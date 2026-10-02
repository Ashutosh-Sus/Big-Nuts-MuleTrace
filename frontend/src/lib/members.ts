// Case member lists: flagged members first (in the server's order: role, then score), then the rest. In a
// large case hundreds of likely origins (victims) would otherwise come before the first mule.
export function flaggedFirst<T extends { flagged: boolean }>(members: T[]): T[] {
  return [...members.filter((m) => m.flagged), ...members.filter((m) => !m.flagged)];
}
