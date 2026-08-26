// The one control a VISITOR may touch on surface A. Deliberately not the
// operator UI: no hiding, no camera modes, no zoom slider, no density.
//
// Why "Übersicht" is here: after a minute of pinching around, a visitor is
// lost, and the next visitor inherits a random close-up of one node. This is
// the way out of that with one press, and it is the ONLY way out other than
// waiting 30 s for the idle timeout (touch-autonomy.js).
//
// Why it is allowed to be here: it changes nothing beyond this screen. Like
// the camera's manual override it posts nothing — it points the local view
// back at the whole net.
//
// The density steps used to sit here too, and they posted `/api/min_mentions`.
// The reasoning was that "where the camera looks" is local while "what the wall
// means" holds everywhere. That is true of the OPERATOR, who has the dial
// anyway, and false of a stranger in the foyer: surface A is the touchscreen at
// the entrance and surface C the projection in the plenary room, so a guest
// pressing "häufig (ab 3)" was rewriting the wall in front of a seated
// audience. Removed 2026-08-26 (Birk). The density is the operator's, and the
// per-step term counts that used to sit on these buttons moved to the operator
// dropdown with it.

export function createTouchControls(container, { onOverview } = {}) {
  const bar = document.createElement('div');
  bar.className = 'touch-controls';
  bar.id = 'touch-controls';

  const overview = document.createElement('button');
  overview.id = 'touch-overview';
  overview.className = 'touch-button';
  // Not "Zoom 1x": the visitor is not thinking in zoom factors, they are
  // thinking "show me everything again".
  overview.textContent = 'Übersicht';
  overview.addEventListener('click', () => onOverview && onOverview());
  bar.appendChild(overview);

  container.appendChild(bar);

  return { element: bar };
}
