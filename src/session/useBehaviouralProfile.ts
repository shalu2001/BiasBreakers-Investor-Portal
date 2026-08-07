import { useEffect, useState } from 'react';
import { useSession } from './SessionContext';
import { profileToPersona, type TraitConfidence } from './profileToPersona';
import { getProfile } from '../api/portal';
import type { PersonaProfile } from '../api/persona';
import { PERSONA_FIXTURE } from '../mocks/fixtures';

// Shared loader for the signed-in user's behavioural profile: the saved Cosmos
// parameters are the source of truth, falling back to the in-session game result
// and finally the mock persona. Used by both the dashboard teaser and the full
// profile page so they always show the same thing.
export function useBehaviouralProfile(): { persona: PersonaProfile; confidence: TraitConfidence } {
  const { profile } = useSession();
  const [persona, setPersona] = useState<PersonaProfile>(
    () => (profile ? profileToPersona(profile) : null) ?? PERSONA_FIXTURE,
  );
  const [confidence, setConfidence] = useState<TraitConfidence>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = await getProfile();
        if (cancelled) return;
        const p = saved.parameters ?? {};
        const conf = (p.confidence ?? {}) as { lambda?: { level?: string }; gamma?: { level?: string } };
        setConfidence({ lambda: conf.lambda?.level, gamma: conf.gamma?.level });
        const mapped =
          p.lambda != null || p.gamma != null
            ? profileToPersona({ alpha: p.alpha ?? null, lambda: p.lambda ?? null, gamma: p.gamma ?? null })
            : null;
        if (mapped) setPersona(mapped);
        else if (profile) setPersona(profileToPersona(profile) ?? PERSONA_FIXTURE);
      } catch {
        if (!cancelled) {
          const mapped = profile ? profileToPersona(profile) : null;
          if (mapped) setPersona(mapped);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [profile]);

  return { persona, confidence };
}
