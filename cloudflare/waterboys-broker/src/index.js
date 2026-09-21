const GITHUB_ISSUER = 'https://token.actions.githubusercontent.com';
const GITHUB_JWKS = 'https://token.actions.githubusercontent.com/.well-known/jwks';
const GITHUB_AUDIENCE = 'waterboys-fantasy-compute';
const DEFAULT_OPS_REPO = 'XoticHaze/waterboys-fantasy-ops';
const MAX_BODY_BYTES = 5 * 1024 * 1024;

const WORKFLOWS = Object.freeze({
  login: 'XoticHaze/waterboys-fantasy-compute/.github/workflows/espn-session-bootstrap.yml@refs/heads/main',
  snapshot: 'XoticHaze/waterboys-fantasy-compute/.github/workflows/snapshot.yml@refs/heads/main',
  execute: 'XoticHaze/waterboys-fantasy-compute/.github/workflows/execute-command.yml@refs/heads/main',
});

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'private, no-store',
      'content-security-policy': "default-src 'none'",
      'referrer-policy': 'no-referrer',
      'x-content-type-options': 'nosniff',
    },
  });
}

function b64urlToBytes(value) {
  const padded = String(value || '')
    .replace(/-/g, '+')
    .replace(/_/g, '/')
    .padEnd(Math.ceil(String(value || '').length / 4) * 4, '=');
  const raw = atob(padded);
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

function decodeJsonSegment(value) {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(value)));
}

async function fetchJwks() {
  const response = await fetch(GITHUB_JWKS, {
    headers: {accept: 'application/json'},
    cf: {cacheTtl: 300, cacheEverything: true},
  });
  if (!response.ok) throw new Error('jwks_unavailable');
  const body = await response.json();
  if (!body || !Array.isArray(body.keys)) throw new Error('jwks_invalid');
  return body.keys;
}

async function verifyRs256Jwt(jwt) {
  const parts = String(jwt || '').split('.');
  if (parts.length !== 3) throw new Error('jwt_invalid');
  const header = decodeJsonSegment(parts[0]);
  const claims = decodeJsonSegment(parts[1]);
  if (header.alg !== 'RS256' || !header.kid) throw new Error('jwt_header_rejected');

  const keys = await fetchJwks();
  const jwk = keys.find((key) => key && key.kid === header.kid && key.kty === 'RSA');
  if (!jwk) throw new Error('jwt_key_unknown');
  const key = await crypto.subtle.importKey(
    'jwk',
    {...jwk},
    {name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256'},
    false,
    ['verify'],
  );
  const ok = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    key,
    b64urlToBytes(parts[2]),
    new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
  );
  if (!ok) throw new Error('jwt_signature_rejected');

  const now = Math.floor(Date.now() / 1000);
  const exp = Number(claims.exp);
  const iat = Number(claims.iat);
  const nbf = claims.nbf === undefined ? iat : Number(claims.nbf);
  if (!Number.isFinite(exp) || !Number.isFinite(iat) || !Number.isFinite(nbf)) {
    throw new Error('jwt_time_invalid');
  }
  if (exp < now - 30 || nbf > now + 30 || iat > now + 30) {
    throw new Error('jwt_time_rejected');
  }
  return claims;
}

function audiences(claims) {
  return Array.isArray(claims.aud) ? claims.aud : [claims.aud];
}

async function verifyCaller(request) {
  const auth = String(request.headers.get('authorization') || '');
  if (!auth.startsWith('Bearer ') || auth.length > 16384) throw new Error('caller_unauthorized');
  const callerRunId = String(request.headers.get('x-waterboys-caller-run-id') || '');
  if (!/^\d{4,24}$/.test(callerRunId)) throw new Error('caller_run_id_rejected');

  const claims = await verifyRs256Jwt(auth.slice(7));
  if (
    claims.iss !== GITHUB_ISSUER
    || !audiences(claims).includes(GITHUB_AUDIENCE)
    || claims.repository !== 'XoticHaze/waterboys-fantasy-compute'
    || claims.ref !== 'refs/heads/main'
    || claims.repository_visibility !== 'public'
    || claims.runner_environment !== 'github-hosted'
    || !['workflow_dispatch', 'schedule', 'repository_dispatch', 'push'].includes(String(claims.event_name || ''))
    || String(claims.run_id || '') !== callerRunId
    || !Object.values(WORKFLOWS).includes(String(claims.workflow_ref || ''))
  ) {
    throw new Error('caller_identity_rejected');
  }
  return {
    run_id: callerRunId,
    workflow_ref: String(claims.workflow_ref || ''),
    event_name: String(claims.event_name || ''),
    workflow_sha: String(claims.workflow_sha || ''),
  };
}

function requireWorkflow(identity, kind) {
  if (identity.workflow_ref !== WORKFLOWS[kind]) {
    throw new Error('workflow_authority_rejected');
  }
}

function githubHeaders(env) {
  const token = String(env.OPS_GITHUB_TOKEN || '');
  if (!token) throw new Error('ops_github_token_missing');
  return {
    'authorization': 'Bearer ' + token,
    'accept': 'application/vnd.github+json',
    'x-github-api-version': '2022-11-28',
    'user-agent': 'waterboys-fantasy-broker/0.1',
  };
}

function bytesToBase64(bytes) {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunk, bytes.length)));
  }
  return btoa(binary);
}

function textToBase64(text) {
  return bytesToBase64(new TextEncoder().encode(text));
}

function base64ToText(value) {
  const raw = atob(String(value || '').replace(/\s/g, ''));
  return new TextDecoder().decode(Uint8Array.from(raw, (char) => char.charCodeAt(0)));
}

async function githubRead(env, path) {
  const repo = String(env.OPS_REPO || DEFAULT_OPS_REPO);
  const url = `https://api.github.com/repos/${repo}/contents/${path}?ref=main`;
  const response = await fetch(url, {headers: githubHeaders(env)});
  if (!response.ok) throw new Error(`github_read_${response.status}`);
  const node = await response.json();
  if (!node || node.type !== 'file' || !node.content) throw new Error('github_file_invalid');
  return {
    sha: String(node.sha || ''),
    text: base64ToText(node.content),
  };
}

async function githubReadOptional(env, path) {
  try {
    return await githubRead(env, path);
  } catch (error) {
    if (String(error && error.message || '') === 'github_read_404') return null;
    throw error;
  }
}

async function githubWrite(env, path, value, message) {
  const repo = String(env.OPS_REPO || DEFAULT_OPS_REPO);
  const current = await githubReadOptional(env, path);
  const body = {
    message,
    content: textToBase64(JSON.stringify(value, null, 2) + '\n'),
    branch: 'main',
  };
  if (current && current.sha) body.sha = current.sha;
  const response = await fetch(
    `https://api.github.com/repos/${repo}/contents/${path}`,
    {
      method: 'PUT',
      headers: {...githubHeaders(env), 'content-type': 'application/json'},
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 1000);
    throw new Error(`github_write_${response.status}:${detail}`);
  }
  const node = await response.json();
  return String(node && node.commit && node.commit.sha || '');
}

async function readPrivateJson(env, path) {
  const file = await githubRead(env, path);
  return JSON.parse(file.text);
}

async function readJsonBody(request) {
  const length = Number(request.headers.get('content-length') || 0);
  if (length > MAX_BODY_BYTES) throw new Error('body_too_large');
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) throw new Error('body_too_large');
  return text ? JSON.parse(text) : {};
}

function validateSnapshot(node, league) {
  if (!node || node.schema !== 'waterboys.snapshot.v1' || node.status !== 'ok') {
    throw new Error('snapshot_schema_rejected');
  }
  const privacy = node.privacy && typeof node.privacy === 'object' ? node.privacy : {};
  if (
    privacy.credentials_included !== false
    || privacy.tokens_included !== false
    || privacy.cookies_included !== false
  ) {
    throw new Error('snapshot_privacy_rejected');
  }
  if (!Array.isArray(node.teams) || !Array.isArray(node.free_agents) || !node.waterboys) {
    throw new Error('snapshot_shape_rejected');
  }
  if (Number(league.league_size || 0) && node.teams.length !== Number(league.league_size)) {
    throw new Error('snapshot_team_count_rejected');
  }
  const raw = JSON.stringify(node).toLowerCase();
  if (raw.includes('espn_s2') || raw.includes('swid') || raw.includes('ops_github_token')) {
    throw new Error('snapshot_secret_marker_rejected');
  }
}

function safeName(value) {
  return String(value || 'unknown').replace(/[^a-zA-Z0-9_.-]/g, '_').slice(0, 160);
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      if (request.method !== 'POST') return json({error: 'method_not_allowed'}, 405);

      const identity = await verifyCaller(request);

      if (url.pathname === '/v1/login-bootstrap') {
        requireWorkflow(identity, 'login');
        const league = await readPrivateJson(env, 'config/league.json');
        if (league.ready !== true || Number(league.league_id || 0) <= 0) {
          return json({error: 'league_config_not_ready'}, 409);
        }
        const username = String(env.ESPN_USERNAME || '');
        const password = String(env.ESPN_PASSWORD || '');
        if (!username || !password) {
          return json({error: 'espn_login_credentials_not_ready'}, 503);
        }
        return json({
          username,
          password,
          league: {
            league_id: Number(league.league_id),
            season: Number(league.season),
            league_size: Number(league.league_size),
            team_name: String(league.team_name || ''),
          },
        });
      }

      if (url.pathname === '/v1/runtime-config') {
        if (![WORKFLOWS.snapshot, WORKFLOWS.execute].includes(identity.workflow_ref)) {
          throw new Error('workflow_authority_rejected');
        }
        const league = await readPrivateJson(env, 'config/league.json');
        const policy = await readPrivateJson(env, 'config/policy.json');
        if (league.ready !== true || Number(league.league_id || 0) <= 0) {
          return json({error: 'league_config_not_ready'}, 409);
        }
        const espnS2 = String(env.ESPN_S2 || '');
        const swid = String(env.ESPN_SWID || '');
        if (!espnS2 || !swid) return json({error: 'espn_credentials_not_ready'}, 503);
        return json({league, policy, espn_s2: espnS2, swid});
      }

      if (url.pathname === '/v1/snapshot') {
        requireWorkflow(identity, 'snapshot');
        const league = await readPrivateJson(env, 'config/league.json');
        const snapshot = await readJsonBody(request);
        validateSnapshot(snapshot, league);
        const latestSha = await githubWrite(
          env,
          'state/latest.json',
          snapshot,
          `snapshot: refresh WaterBoys state from run ${identity.run_id}`,
        );
        const stamp = safeName(snapshot.collected_at);
        await githubWrite(
          env,
          `history/snapshots/${stamp}-run-${identity.run_id}.json`,
          snapshot,
          `snapshot: archive WaterBoys state from run ${identity.run_id}`,
        );
        return json({ok: true, state_commit: latestSha, run_id: identity.run_id});
      }

      if (url.pathname === '/v1/command/next') {
        requireWorkflow(identity, 'execute');
        return json(await readPrivateJson(env, 'control/pending-command.json'));
      }

      if (url.pathname === '/v1/receipt') {
        requireWorkflow(identity, 'execute');
        const receipt = await readJsonBody(request);
        if (!receipt || receipt.schema !== 'waterboys.execution_receipt.v1') {
          throw new Error('receipt_schema_rejected');
        }
        const commandId = safeName(receipt.command_id || 'no-command');
        const latestSha = await githubWrite(
          env,
          'receipts/latest.json',
          receipt,
          `receipt: record WaterBoys execution run ${identity.run_id}`,
        );
        await githubWrite(
          env,
          `history/receipts/${commandId}-run-${identity.run_id}.json`,
          receipt,
          `receipt: archive WaterBoys execution run ${identity.run_id}`,
        );
        return json({ok: true, receipt_commit: latestSha, run_id: identity.run_id});
      }

      return json({error: 'not_found'}, 404);
    } catch (error) {
      const message = String(error && error.message || 'request_failed');
      const unauthorized = (
        message.includes('caller_')
        || message.includes('jwt_')
        || message.includes('workflow_authority')
      );
      return json({error: unauthorized ? 'unauthorized' : message}, unauthorized ? 401 : 400);
    }
  },
};
