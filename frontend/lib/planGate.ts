export const PLAN_LEVELS: Record<string, number> = {
  FREE: 0,
  PRO: 1,
  ENTERPRISE: 2,
  TRIAL: 1,
};

export interface PlanGateUser {
  plan?: string | null;
  is_trial?: boolean;
  trial_status?: string | null;
  trial_expires_at?: string | null;
}

/**
 * Returns true if the user is on a trial whose status is EXPIRED or whose
 * trial_expires_at timestamp is in the past (or unparseable).
 */
export function isTrialExpired(
  user: PlanGateUser | null | undefined,
  now: Date = new Date()
): boolean {
  if (!user) return false;
  if (user.plan === "TRIAL" || user.is_trial) {
    if (user.trial_status === "EXPIRED") {
      return true;
    }
    if (user.trial_expires_at) {
      const expiresAt = new Date(user.trial_expires_at);
      if (!(expiresAt > now)) {
        return true;
      }
    }
  }
  return false;
}

/**
 * Computes the effective numeric tier level for a user, dropping expired
 * trials back to FREE (0) and mapping active TRIAL users to PRO (1).
 */
export function getUserPlanLevel(
  user: PlanGateUser | null | undefined,
  now: Date = new Date()
): number {
  if (isTrialExpired(user, now)) {
    return 0;
  }
  if (user?.is_trial && (!user.plan || user.plan === "FREE")) {
    return PLAN_LEVELS.TRIAL;
  }
  return PLAN_LEVELS[user?.plan ?? "FREE"] ?? 0;
}
