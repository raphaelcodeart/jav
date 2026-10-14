"use client";

/** I pezzi che ogni checkout dello Shop ripete: il campo etichettato, il
 *  passo numerato, la formattazione del denaro e lo sconto bonifico.
 *
 *  Solo presentazione e aritmetica pura, niente stato e niente chiamate: è il
 *  motivo per cui stanno qui e non dentro una delle finestre. Le finestre --
 *  prodotto singolo e carrello -- restano separate finché la prova sul campo
 *  non dice che si somigliano davvero abbastanza da fonderle.
 */

export type DeliveryAddress = {
  recipient_name: string;
  recipient_phone: string;
  address_line1: string;
  address_line2: string;
  city: string;
  province: string;
  postal_code: string;
};

export const inputClass = "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-brand-500";

export function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

export function javCash(cents: number): string {
  return `${(cents / 100).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} JavCash`;
}

/** Rispecchia rules.bank_transfer_discount_cents: la percentuale del residuo,
 *  mezzo centesimo per eccesso. È un'anteprima -- il server la ricalcola e la
 *  congela sull'ordine, e la sua è quella che vale. */
export function bankTransferDiscount(residualCents: number, percentage: number): number {
  if (residualCents <= 0 || percentage <= 0) return 0;
  return Math.floor((residualCents * percentage + 50) / 100);
}

/** Un indirizzo abbastanza completo da poter essere spedito. Gli stessi
 *  minimi che controlla il server, così il pulsante non si accende per poi
 *  far rifiutare l'ordine. */
export function addressComplete(address: DeliveryAddress): boolean {
  return (
    address.recipient_name.trim().length >= 2 &&
    address.recipient_phone.trim().length >= 6 &&
    address.address_line1.trim().length >= 3 &&
    !!address.city.trim() &&
    !!address.province.trim() &&
    address.postal_code.trim().length >= 3
  );
}

export function Field({
  label, children, className = "",
}: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="block font-semibold text-slate-500 uppercase tracking-wide mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}

export function Section({
  n, title, done, children,
}: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl border border-slate-200 space-y-3">
      <div className="flex items-center gap-2.5">
        <span
          className={`flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-bold shrink-0 text-white ${
            done ? "bg-emerald-500" : "bg-brand-600"
          }`}
        >
          {done ? "✓" : n}
        </span>
        <p className="text-sm font-semibold text-slate-900">{title}</p>
      </div>
      {children}
    </div>
  );
}

/** Il modulo dell'indirizzo di consegna, identico in ogni checkout dei
 *  Marketplace: se cambia una etichetta deve cambiare in tutti. */
export function AddressFields({
  address, onChange,
}: { address: DeliveryAddress; onChange: (next: DeliveryAddress) => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-6 gap-3">
      <Field label="Nome e cognome" className="sm:col-span-3">
        <input className={inputClass} value={address.recipient_name} maxLength={50} autoComplete="name"
          onChange={(e) => onChange({ ...address, recipient_name: e.target.value })} />
      </Field>
      <Field label="Telefono (per il corriere)" className="sm:col-span-3">
        <input className={inputClass} value={address.recipient_phone} maxLength={20} inputMode="tel" autoComplete="tel"
          onChange={(e) => onChange({ ...address, recipient_phone: e.target.value })} />
      </Field>
      <Field label="Indirizzo e numero civico" className="sm:col-span-4">
        <input className={inputClass} value={address.address_line1} maxLength={255} autoComplete="address-line1"
          onChange={(e) => onChange({ ...address, address_line1: e.target.value })} />
      </Field>
      <Field label="Scala, interno (facoltativo)" className="sm:col-span-2">
        <input className={inputClass} value={address.address_line2} maxLength={255} autoComplete="address-line2"
          onChange={(e) => onChange({ ...address, address_line2: e.target.value })} />
      </Field>
      <Field label="CAP" className="sm:col-span-2">
        <input className={inputClass} value={address.postal_code} maxLength={12} inputMode="numeric" autoComplete="postal-code"
          onChange={(e) => onChange({ ...address, postal_code: e.target.value })} />
      </Field>
      <Field label="Città" className="sm:col-span-3">
        <input className={inputClass} value={address.city} maxLength={50} autoComplete="address-level2"
          onChange={(e) => onChange({ ...address, city: e.target.value })} />
      </Field>
      <Field label="Provincia" className="sm:col-span-1">
        <input className={inputClass} value={address.province} maxLength={50} placeholder="MI"
          onChange={(e) => onChange({ ...address, province: e.target.value.toUpperCase() })} />
      </Field>
    </div>
  );
}
