/** Il cookie con il club in cui lo staff della piattaforma è "entrato" dal
 * pannello Club. Lo legge il proxy BFF (app/api/proxy) per mandarlo all'API;
 * non è un segreto né un permesso: l'API verifica da sola chi può entrare
 * dove (apps/api/app/domains/club/scope.py). */
export const CLUB_COOKIE = "jav_club";

export function enterClub(clubId: string) {
  document.cookie = `${CLUB_COOKIE}=${clubId}; path=/; SameSite=Lax`;
}

export function leaveClub() {
  document.cookie = `${CLUB_COOKIE}=; path=/; Max-Age=0; SameSite=Lax`;
}

/** Il club scelto entrando nell'area del treinador, per chi allena in più
 *  club (club/staff_clubs.py). Il proxy BFF lo manda come `X-Jav-Staff-Club`;
 *  l'API lo usa solo sulle rotte del treinador e lo verifica da sola contro
 *  le appartenenze attive. Dura quanto il browser aperto: domani si sceglie
 *  di nuovo, come chiede il club. */
export const STAFF_CLUB_COOKIE = "jav_staff_club";
const STAFF_CLUB_EVENT = "jav-staff-club-change";

export function enterStaffClub(clubId: string) {
  document.cookie = `${STAFF_CLUB_COOKIE}=${clubId}; path=/; SameSite=Lax`;
  window.dispatchEvent(new Event(STAFF_CLUB_EVENT));
}

export function leaveStaffClub() {
  document.cookie = `${STAFF_CLUB_COOKIE}=; path=/; Max-Age=0; SameSite=Lax`;
  window.dispatchEvent(new Event(STAFF_CLUB_EVENT));
}

export function readStaffClub(): string | null {
  const hit = document.cookie.split("; ").find((c) => c.startsWith(`${STAFF_CLUB_COOKIE}=`));
  return hit ? decodeURIComponent(hit.slice(STAFF_CLUB_COOKIE.length + 1)) || null : null;
}

/** Per useSyncExternalStore: il cookie cambia solo da enter/leave qui sopra. */
export function subscribeStaffClub(onChange: () => void) {
  window.addEventListener(STAFF_CLUB_EVENT, onChange);
  return () => window.removeEventListener(STAFF_CLUB_EVENT, onChange);
}
