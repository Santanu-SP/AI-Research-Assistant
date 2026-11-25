import { describe, expect, it } from 'vitest';
import { redactSecrets } from './modelErrors';

describe('redactSecrets', () => {
  it('hides both Google key formats', () => {
    // Fake keys, built in pieces so secret scanners do not flag this test.
    const oldKey = 'AIza' + 'SyA1234567890abcdefghijklmnopqr';
    const newKey = 'AQ.' + 'Ab8Fake1234567890abcdefghijklmnop';
    const cleaned = redactSecrets(`bad key ${oldKey} and ${newKey}`);
    expect(cleaned).not.toContain('SyA1234');
    expect(cleaned).not.toContain('Ab8Fake');
    expect(cleaned.match(/\[hidden\]/g)).toHaveLength(2);
  });
});
