// SPDX-License-Identifier: AGPL-3.0-only
// Boards 9 and 10: How we calculate (FR-UI-17) and Terms/Privacy (drafts until legal review).
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { TopBar } from "../components/Shell";
import { goBack, navigate } from "../lib/router";

function Page({ title, eyebrow, children }: { title: string; eyebrow: string; children: ReactNode }) {
  return (
    <div>
      <TopBar right={<button type="button" className="lnk" onClick={() => goBack("/")}>← Back</button>} />
      <main className="wrap" style={{ maxWidth: 880, display: "flex", flexDirection: "column", gap: 28, paddingBottom: 96 }}>
        <div className="eyebrow" style={{ color: "var(--gold)" }}>{eyebrow}</div>
        <h1 className="h1m">{title}</h1>
        {children}
      </main>
    </div>
  );
}
function H({ children }: { children: ReactNode }) { return <h2 className="h2g" style={{ marginTop: 12 }}>{children}</h2>; }
function P({ children }: { children: ReactNode }) { return <p className="lead">{children}</p>; }
function L({ items }: { items: ReactNode[] }) {
  return <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 10, fontSize: 17, lineHeight: 1.65, color: "var(--text2)" }}>{items.map((x, i) => <li key={i}>{x}</li>)}</ul>;
}

export function HowWeCalculate() {
  const [providers, setProviders] = useState<string[] | null>(null);
  useEffect(() => { api.version().then((v) => setProviders(v.ai_providers)).catch(() => setProviders(null)); }, []);
  const aiLine = providers === null ? "The AI services in use are listed here when the server is reachable."
    : providers.length ? `The AI services we use today are ${providers.join(" and ")}, on their free tiers.`
    : "No AI service is switched on right now, so every card shows our reviewed library text.";
  return (
    <Page title="How we calculate" eyebrow="Method">
      <P>Pranix reads your birth chart with fixed, published rules. A computer program does all the astronomy and all the maths. AI is only ever used to word reflections from facts the program has already worked out, and it never calculates anything.</P>
      <H>The sky model</H>
      <L items={[
        <><strong>Planet positions:</strong> Swiss Ephemeris, the astronomical library many astrology programs use. Covers births from 1800 onwards.</>,
        <><strong>Zodiac:</strong> sidereal (star-based), with the Lahiri ayanamsa, the standard in Indian astrology. The exact value used is shown under your chart.</>,
        <><strong>Houses:</strong> whole-sign. The rising sign is house one, the next sign house two, and so on.</>,
        <><strong>Rahu and Ketu:</strong> mean node. Ketu is always exactly opposite Rahu.</>,
        <><strong>Your birth time:</strong> converted to universal time with the historical time-zone rules of your birthplace, including old daylight-saving changes. If a clock time happened twice or never, we ask you which one.</>,
      ]} />
      <H>Your D1 and D9 charts</H>
      <L items={["D1 (birth chart, kundli): the rising sign and the sign and degree of all nine planets at your birth, drawn in North Indian style. Retrograde planets are marked ℞.",
        "D9 (navamsa): worked out from the D1 degrees with no new astronomy. Each sign is split into nine parts of 3°20′, and each part belongs to a sign by a classical rule. The D9 rising sign changes about every quarter of an hour, so it needs an accurate birth time.",
        "Degrees are cut to the minute, never rounded up, so the screen never shows a planet in a part it has not reached yet."]} />
      <H>Birth star and naming syllable</H>
      <P>Your birth star (nakshatra) is where the Moon was among the twenty-seven lunar mansions, each split into four quarters. The naming syllable comes from a traditional table linking each quarter to a sound; regional tables differ in a few syllables, so we name ours (naming-core@1, a common North-Indian table). It is a custom, never a judgement on your name, and your name is never sent to us for it.</P>
      <H>Life periods (Vimshottari Dasha)</H>
      <P>Nine planetary periods in a fixed order adding up to one hundred and twenty years, starting from the Moon's exact position at birth, with a year of 365.25 days. The shortest levels last days or hours, so they are only as precise as your birth minute. Periods describe themes to reflect on; we never predict events.</P>
      <H>Our own rules</H>
      <L items={["Classical texts do not give exact percentages for elements, doshas or energy centres. To show them we made our own rules, and we say so plainly.",
        "Elements: each planet and sign adds to an element, weighted by placement and dignity, then scaled to one hundred.",
        "Body-mind tendencies (doshas): from the elements of your rising, Moon and Sun signs and their lords. Tendencies to reflect on, not a diagnosis or health advice.",
        "Energy centres (chakras): each centre is linked with a planet; how comfortable that planet is in its sign sets the centre as dominant, balanced or quieter.",
        "Without a birth time the rising sign is left out: doshas then use the Moon and Sun only."]} />
      <H>Deity, colours and days</H>
      <L items={["Deity: from your soul planet's sign in the D9 chart and the twelfth sign from it, following a Jaimini method. Traditions differ; we show one main form and up to two others.",
        "Colours and days: from the planets that rule your chart (rising-sign lord, Moon-sign lord and soul planet) and their traditional colours and weekdays. Associations for reflection, never guarantees, and never \"lucky\"."]} />
      <H>If you do not know your birth time</H>
      <P>One rule: show only what is certain. We check your whole birth day. A planet's sign or star that stayed the same all day is shown; one that changed is shown with both options. Anything else that depends on the hour (the charts, houses, the deity, and your life periods if they change during the day) is left out rather than guessed.</P>
      <H>What AI does, and does not do</H>
      <L items={["Most card text comes from a library written and reviewed by people (badge: Curated).",
        "Some cards may be reworded by AI from the chart facts and library text (badge: AI-phrased). Automatic checks reject any wording with numbers, unlisted facts, fear or medical claims; then the reviewed text is shown instead.",
        aiLine, "AI never sees your name, birth date, time or place. It receives only anonymous chart facts such as \"Moon in Taurus\".",
        "No predictions of events, health, money or relationships. No gemstones or paid remedies."]} />
      <H>Who checked this</H>
      <P>The lookup tables (stars, dignities, deities, colours, weekdays, naming syllables) were checked by the project owner against trusted sources. The full rule sheets are reviewed again before launch. This is a careful community project, not a certification by a professional astrologer.</P>
      <H>Source code and credits</H>
      <L items={[<>Pranix is open source under the GNU Affero General Public License v3: <a href="https://github.com/iamrajharshit/Pranix" rel="noopener">source code</a>.</>,
        "Swiss Ephemeris by Astrodienst (AGPL). Place names from GeoNames (CC BY 4.0). Time zones from timezone-boundary-builder (ODbL). Map tiles © OpenStreetMap contributors.",
        "Fonts: Cormorant Garamond and Inter (SIL Open Font License)."]} />
    </Page>
  );
}

export function Legal() {
  const [tab, setTab] = useState<"privacy" | "terms">(new URLSearchParams(window.location.search).get("tab") === "terms" ? "terms" : "privacy");
  const choose = (t: "privacy" | "terms") => { setTab(t); navigate(t === "terms" ? "/legal?tab=terms" : "/legal", true); };
  return (
    <Page title="Terms and Privacy" eyebrow="Plain language">
      <div role="note" style={{ background: "rgba(255,217,160,.08)", border: "1px solid rgba(255,217,160,.5)", borderRadius: 16, padding: "14px 18px", fontSize: 15, lineHeight: 1.6, color: "#FFE7C2" }}>
        Draft (privacy p-0.1, terms t-0.1). These texts are in plain language and will be reviewed by a lawyer before accounts open.
      </div>
      <div role="tablist" aria-label="Document" style={{ display: "flex", gap: 10 }}>
        <button type="button" role="tab" className="tab" aria-selected={tab === "privacy"} onClick={() => choose("privacy")}>Privacy notice</button>
        <button type="button" role="tab" className="tab" aria-selected={tab === "terms"} onClick={() => choose("terms")}>Terms of use</button>
      </div>
      {tab === "privacy" ? (<>
        <H>If you use Pranix as a guest</H>
        <L items={["Nothing is saved to an account. Your birth details are used to compute your chart, which is kept in our server's memory for up to a day so the page can reload, then forgotten.",
          "Your name and pronouns never leave your browser.", "Your browser keeps your draft details in this tab only (session storage) and forgets them when you close the tab."]} />
        <H>The optional map</H>
        <P>If you choose "Pick on a map", your browser loads map pictures from OpenStreetMap. Like any website, the map provider sees which area you look at and your IP address. It never receives your name, birth date or time. Looking up the nearest town and time zone happens on our own server. If you search or type coordinates instead, no map is loaded.</P>
        <H>What goes to AI providers</H>
        <P>Only anonymous chart facts (such as "Moon in Taurus") to word some cards. Never your name, email, birth date, time or place. The providers are named on the How we calculate page; some free AI services may use what they receive to improve their products, which is why we send so little.</P>
        <H>What we never do</H>
        <L items={["No advertising or tracking cookies.", "No selling or sharing of your data.", "No birth details, names or emails in our logs."]} />
        <H>Age</H><P>Pranix is for people aged eighteen or over, and charts can only be made for people aged eighteen or over.</P>
        <H>Contact</H><P>Questions about your data: a contact address will be added before launch.</P>
      </>) : (<>
        <H>What Pranix is</H>
        <P>A free tool for self-reflection using traditional Vedic astrology and Ayurvedic ideas. It does not predict events and it is not medical, psychological, financial or legal advice. Please do not make important decisions based on it.</P>
        <H>Who can use it</H><P>You must be eighteen or older.</P>
        <H>Fair use</H><L items={["Please do not overload the service or automate requests; we limit how often requests can be made.", "Do not use Pranix to harass or profile other people."]} />
        <H>Availability</H><P>Pranix runs on free hosting. It may sleep, slow down or pause, for example at the end of a month. We try to tell you clearly when that happens.</P>
        <H>Open source</H><P>The code is published under the GNU Affero General Public License v3. You can read and reuse it under that licence.</P>
        <H>Liability and governing law</H><P>To be written with legal review before launch.</P>
      </>)}
    </Page>
  );
}
