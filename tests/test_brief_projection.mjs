import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(
  new URL('../cloudflare/waterboys-broker/src/index.js', import.meta.url),
  'utf8',
);
const { buildBrief } = await import(
  'data:text/javascript;base64,' + Buffer.from(source).toString('base64')
);

test('private compact brief retains bounded elimination and FAAB intelligence', () => {
  const team = (i) => ({
    team_id: i, name: 'Team ' + i, projected_points: 110 + i,
    projection_rank: i, gap_above_projected_low: i,
    relative_elimination_risk_share: 0.1, forecast_tier: 'monitor',
    priority_release_targets: [{ player_id: i, name: 'Target ' + i, recommended_bid: 20 }],
  });
  const candidate = {
    player_id: 42, name: 'Target RB', position: 'RB',
    bid_guidance: { recommended: 28, reservation_ceiling: 75 },
    faab_market_intelligence: {
      clearing_price_reference: { median: 20, p75: 25, p90: 40 },
      failed_demand_pressure: { sample_size: 1, clearing_price_eligible: false },
      budget_competition: { competitor_count: 8 },
    },
  };
  const release = (i) => ({
    ...candidate, player_id: i, source_team_id: 7,
    source_team: 'Cappsized', forecast_weighted_remaining_value: 100 - i,
  });
  const snapshot = {
    collected_at: '2026-10-22T20:12:09Z',
    league: {}, waterboys: {}, value_engine: { waiver_targets: [candidate] },
    placement_engine: {
      elimination_pool_forecast: {
        method: 'relative-risk', not_calibrated_probability: true,
        projected_low: 84.61, teams: Array.from({ length: 6 }, (_, i) => team(i + 1)),
        release_board: Array.from({ length: 30 }, (_, i) => release(i)),
      },
      faab_market_state: {
        waterboys_available_faab: 891, budget_rank_if_all_bid: 5,
        competitor_count: 11, competitors_capable_at_target_bid: 8,
      },
    },
  };
  const brief = buildBrief(snapshot, 'run-1', 'commit-1');
  assert.equal(brief.placement_engine.elimination_pool_forecast.teams.length, 5);
  assert.equal(brief.placement_engine.elimination_pool_forecast.release_board.length, 25);
  assert.equal(brief.placement_engine.elimination_pool_forecast.not_calibrated_probability, true);
  assert.equal(brief.placement_engine.elimination_pool_forecast.teams[0].name, 'Team 1');
  assert.equal(brief.placement_engine.elimination_pool_forecast.release_board[0].forecast_weighted_remaining_value, 100);
  assert.deepEqual(
    brief.placement_engine.elimination_pool_forecast.release_board[0].faab_market_intelligence,
    candidate.faab_market_intelligence,
  );
  assert.equal(brief.placement_engine.faab_market_state.waterboys_available_faab, 891);
  assert.equal(brief.placement_engine.faab_market_state.competitor_count, 11);
  assert.deepEqual(brief.value_engine.waiver_targets[0].faab_market_intelligence, candidate.faab_market_intelligence);
  assert.deepEqual(brief.value_engine.waiver_targets[0].bid_guidance, candidate.bid_guidance);
});

test('older snapshots lacking intelligence still produce a safe empty brief', () => {
  const brief = buildBrief({
    league: {}, waterboys: {}, value_engine: {}, placement_engine: {},
  }, 'old-run', 'old-commit');
  assert.deepEqual(brief.placement_engine.elimination_pool_forecast.teams, []);
  assert.deepEqual(brief.placement_engine.elimination_pool_forecast.release_board, []);
  assert.deepEqual(brief.placement_engine.faab_market_state, {});
});
