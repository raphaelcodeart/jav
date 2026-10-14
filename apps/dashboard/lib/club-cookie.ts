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
