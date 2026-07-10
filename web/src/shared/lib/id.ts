let clientIdCounter = 0;

export function createClientId(scope: string): string {
  clientIdCounter += 1;
  return `xuanmu-${scope}-${Date.now().toString(36)}-${clientIdCounter.toString(36)}`;
}
