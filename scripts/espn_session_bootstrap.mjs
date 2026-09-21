import fs from 'node:fs';
import process from 'node:process';
import { chromium } from 'playwright';

const BROKER_URL = String(process.env.WATERBOYS_BROKER_URL || '').replace(/\/$/, '');
const outputPath = process.argv[2];
if (!BROKER_URL || !outputPath) {
  throw new Error('bootstrap configuration missing');
}

function marker(name, value) {
  process.stdout.write(`${name}=${value}\n`);
}

async function githubOidcToken() {
  const raw = process.env.ACTIONS_ID_TOKEN_REQUEST_URL;
  const bearer = process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN;
  if (!raw || !bearer) throw new Error('github_oidc_environment_missing');
  const url = new URL(raw);
  url.searchParams.set('audience', 'waterboys-fantasy-compute');
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${bearer}`,
      Accept: 'application/json',
    },
  });
  if (!response.ok) throw new Error(`github_oidc_http_${response.status}`);
  const node = await response.json();
  const token = String(node.value || '');
  if (token.split('.').length !== 3) throw new Error('github_oidc_token_invalid');
  return token;
}

async function fetchLoginBootstrap() {
  const token = await githubOidcToken();
  const response = await fetch(BROKER_URL + '/v1/login-bootstrap', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-WaterBoys-Caller-Run-Id': String(process.env.GITHUB_RUN_ID || ''),
    },
    body: '{}',
  });
  if (!response.ok) {
    let detail = '';
    try {
      const node = await response.json();
      detail = String(node.error || '');
    } catch {}
    throw new Error(`login_broker_http_${response.status}:${detail}`);
  }
  const node = await response.json();
  if (
    !node
    || typeof node.username !== 'string'
    || !node.username
    || typeof node.password !== 'string'
    || !node.password
    || !node.league
  ) {
    throw new Error('login_broker_payload_invalid');
  }
  return node;
}

async function fetchLoginOtp() {
  const token = await githubOidcToken();
  const response = await fetch(BROKER_URL + '/v1/login-otp', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-WaterBoys-Caller-Run-Id': String(process.env.GITHUB_RUN_ID || ''),
    },
    body: '{}',
  });
  if (!response.ok) throw new Error(`login_otp_broker_http_${response.status}`);
  const node = await response.json();
  const otp = String(node?.otp || '').trim();
  return node?.ready === true && /^\d{6,8}$/.test(otp) ? otp : '';
}

async function waitForLoginOtp(page, timeoutMs, baselineOtp = '') {
  marker('WATERBOYS_ESPN_OTP_WAITING', '1');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const otp = await fetchLoginOtp();
    if (otp && otp !== baselineOtp) {
      marker('WATERBOYS_ESPN_OTP_RECEIVED', '1');
      return otp;
    }
    await page.waitForTimeout(2000);
  }
  return '';
}

async function firstVisibleInput(page, selectors) {
  for (const frame of page.frames()) {
    for (const selector of selectors) {
      const locator = frame.locator(selector).first();
      try {
        if (await locator.count() && await locator.isVisible({ timeout: 300 })) {
          return locator;
        }
      } catch {}
    }
  }
  return null;
}

async function firstVisibleButton(page, regex) {
  for (const frame of page.frames()) {
    const locator = frame.getByRole('button', { name: regex }).first();
    try {
      if (await locator.count() && await locator.isVisible({ timeout: 300 })) {
        return locator;
      }
    } catch {}
  }
  return null;
}

async function waitForInput(page, selectors, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = await firstVisibleInput(page, selectors);
    if (found) return found;
    await page.waitForTimeout(500);
  }
  return null;
}

async function maybeClick(page, regex) {
  const button = await firstVisibleButton(page, regex);
  if (!button) return false;
  await button.click();
  return true;
}

async function findOtpTarget(page) {
  const selectors = [
    'input[autocomplete="one-time-code"]',
    'input[name*="otp" i]',
    'input[id*="otp" i]',
    'input[name*="code" i]',
    'input[id*="code" i]',
    'input[name*="passcode" i]',
    'input[id*="passcode" i]',
    'input[aria-label*="code" i]',
    'input[placeholder*="code" i]',
    'input[inputmode="numeric"]',
  ];
  const single = await firstVisibleInput(page, selectors);
  if (single) return { kind: 'single', input: single };

  for (const frame of page.frames()) {
    const loc = frame.locator('input[maxlength="1"]');
    try {
      const count = await loc.count();
      const visible = [];
      for (let i = 0; i < count; i += 1) {
        const item = loc.nth(i);
        if (await item.isVisible({ timeout: 150 })) visible.push(item);
      }
      if (visible.length >= 6) return { kind: 'split', inputs: visible.slice(0, 8) };
    } catch {}
  }
  return null;
}

async function waitForOtpTarget(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const target = await findOtpTarget(page);
    if (target) return target;
    await page.waitForTimeout(500);
  }
  return null;
}

async function fillOtpTarget(target, otp) {
  if (target.kind === 'single') {
    await target.input.fill(otp);
    return;
  }
  for (let i = 0; i < target.inputs.length && i < otp.length; i += 1) {
    await target.inputs[i].fill(otp[i]);
  }
}

async function readSessionCookies(context) {
  const cookies = await context.cookies();
  const s2Cookie = cookies.find((cookie) => cookie.name.toLowerCase() === 'espn_s2');
  const swidCookie = cookies.find((cookie) => cookie.name.toLowerCase() === 'swid');
  return {
    espnS2: String(s2Cookie?.value || ''),
    swid: String(swidCookie?.value || ''),
  };
}

async function bodyHasChallenge(page) {
  const patterns = [
    /verify.*robot/i,
    /captcha/i,
    /verification code/i,
    /security code/i,
    /passcode/i,
    /two[- ]step/i,
    /two[- ]factor/i,
    /confirm.*identity/i,
  ];
  for (const frame of page.frames()) {
    try {
      const text = await frame.locator('body').innerText({ timeout: 500 });
      if (patterns.some((pattern) => pattern.test(text))) return true;
    } catch {}
  }
  return false;
}

const login = await fetchLoginBootstrap();
const baselineOtp = await fetchLoginOtp();
marker('WATERBOYS_ESPN_LOGIN_BROKER', 'accepted');
marker('WATERBOYS_ESPN_OTP_BASELINE_CAPTURED', baselineOtp ? '1' : '0');

const browser = await chromium.launch({
  headless: false,
  args: [
    '--disable-dev-shm-usage',
    '--no-default-browser-check',
    '--no-first-run',
  ],
});

try {
  const context = await browser.newContext({
    locale: 'en-US',
    timezoneId: 'America/Chicago',
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();

  await page.goto('https://www.espn.com/login', {
    waitUntil: 'domcontentloaded',
    timeout: 45000,
  });
  await page.waitForTimeout(2500);

  const usernameSelectors = [
    'input[type="email"]',
    'input[autocomplete="username"]',
    'input[name="loginValue"]',
    'input[name*="email" i]',
    'input[name*="user" i]',
    'input[name*="login" i]',
    'input[id*="email" i]',
    'input[id*="user" i]',
    'input[id*="login" i]',
    'input[placeholder*="email" i]',
    'input[placeholder*="username" i]',
    'input[aria-label*="email" i]',
    'input[aria-label*="username" i]',
  ];
  const passwordSelectors = [
    'input[type="password"]',
    'input[autocomplete="current-password"]',
    'input[name*="password" i]',
    'input[id*="password" i]',
  ];

  const username = await waitForInput(page, usernameSelectors, 20000);
  if (!username) {
    marker(
      'WATERBOYS_ESPN_LOGIN_CHALLENGE',
      (await bodyHasChallenge(page)) ? 'pre_form' : 'username_not_found',
    );
    process.exitCode = 32;
  } else {
    marker('WATERBOYS_ESPN_LOGIN_FORM', 'username_found');
      await username.fill(login.username);
      marker('WATERBOYS_ESPN_LOGIN_FORM', 'username_filled');

      let password = await firstVisibleInput(page, passwordSelectors);
      if (!password) {
        await maybeClick(page, /continue|next|log in|sign in/i);
        password = await waitForInput(page, passwordSelectors, 15000);
      }
      if (!password) {
        const switched = await maybeClick(page, /use.*password|password.*instead|sign in.*password|log in.*password/i);
        if (switched) password = await waitForInput(page, passwordSelectors, 10000);
      }

      if (!password) {
        marker(
          'WATERBOYS_ESPN_LOGIN_CHALLENGE',
          (await bodyHasChallenge(page)) ? 'after_username' : 'password_not_found',
        );
        process.exitCode = 33;
      } else {
        await password.fill(login.password);
        marker('WATERBOYS_ESPN_LOGIN_FORM', 'password_filled');
        const submitted = await maybeClick(page, /log in|sign in|continue|submit/i);
        if (!submitted) {
          await password.press('Enter');
        }

        let { espnS2, swid } = await readSessionCookies(context);
        const firstDeadline = Date.now() + 15000;
        let otpTarget = null;
        while (Date.now() < firstDeadline && (!espnS2 || !swid)) {
          otpTarget = await findOtpTarget(page);
          if (otpTarget) break;
          await page.waitForTimeout(750);
          ({ espnS2, swid } = await readSessionCookies(context));
        }

        if ((!espnS2 || !swid) && otpTarget) {
          marker('WATERBOYS_ESPN_LOGIN_CHALLENGE', 'otp_required');
          const otp = await waitForLoginOtp(page, 8 * 60 * 1000, baselineOtp);
          if (!otp) {
            marker('WATERBOYS_ESPN_OTP_RESULT', 'timeout');
            process.exitCode = 37;
          } else {
            await fillOtpTarget(otpTarget, otp);
            marker('WATERBOYS_ESPN_OTP_RESULT', 'submitted');
            const verified = await maybeClick(page, /verify|continue|submit|next|log in|sign in/i);
            if (!verified && otpTarget.kind === 'single') {
              await otpTarget.input.press('Enter');
            }

            const otpDeadline = Date.now() + 45000;
            while (Date.now() < otpDeadline && (!espnS2 || !swid)) {
              await page.waitForTimeout(1000);
              ({ espnS2, swid } = await readSessionCookies(context));
            }
          }
        }

        if (!espnS2 || !swid) {
          marker(
            'WATERBOYS_ESPN_LOGIN_CHALLENGE',
            (await bodyHasChallenge(page)) ? 'after_verification' : 'session_cookie_missing',
          );
          process.exitCode = process.exitCode || 34;
        } else {
          const leagueId = Number(login.league.league_id);
          const season = Number(login.league.season);
          const expectedTeams = Number(login.league.league_size);
          const url =
            `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${season}/segments/0/leagues/${leagueId}?view=mTeam`;
          const response = await context.request.get(url, { timeout: 30000 });
          marker('WATERBOYS_ESPN_SESSION_HTTP', String(response.status()));

          if (!response.ok()) {
            marker('WATERBOYS_ESPN_SESSION_VALID', '0');
            process.exitCode = 35;
          } else {
            const node = await response.json();
            const teams = Array.isArray(node?.teams) ? node.teams : [];
            marker('WATERBOYS_ESPN_SESSION_TEAM_COUNT', String(teams.length));
            if (expectedTeams && teams.length !== expectedTeams) {
              marker('WATERBOYS_ESPN_SESSION_VALID', '0');
              process.exitCode = 36;
            } else {
              const payload = JSON.stringify({ espn_s2: espnS2, swid }, null, 2) + '\n';
              fs.writeFileSync(outputPath, payload, { encoding: 'utf8', mode: 0o600 });
              fs.chmodSync(outputPath, 0o600);
              marker('WATERBOYS_ESPN_SESSION_VALID', '1');
              marker('WATERBOYS_ESPN_SESSION_COOKIES_CAPTURED', '2');
            }
          }
        }
      }
    }
} finally {
  await browser.close();
}
