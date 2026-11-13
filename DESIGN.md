---
name: Enterprise Knowledge AI Agent
description: A calm ink-and-jade workspace where the only strong colour is the mark of a verified answer.
colors:
  jade: "#0b7a66"
  jade-ink: "#075c4d"
  jade-mist: "#e2f2ed"
  jade-line: "#b3dbcf"
  on-jade: "#ffffff"
  verified: "#14866a"
  verified-ink: "#0b6450"
  verified-mist: "#e2f4ec"
  verified-line: "#a9dcc6"
  amber: "#b7720f"
  amber-ink: "#83510a"
  amber-mist: "#fdf3e1"
  amber-line: "#f0d6a6"
  brick: "#bf3a2c"
  brick-ink: "#972c21"
  brick-mist: "#fcebe8"
  brick-line: "#f3c3bc"
  sage-paper: "#f2f5f4"
  surface: "#ffffff"
  surface-sunk: "#f7f9f8"
  surface-deep: "#ebf0ee"
  hairline: "#dfe6e3"
  hairline-strong: "#c3cec9"
  ink: "#14211d"
  ink-soft: "#2f3e39"
  muted: "#5d6d67"
  faint: "#63736d"
typography:
  display:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "clamp(28px, 3.2vw, 37px)"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "21px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  answer:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.72
  label:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0"
  figure:
    fontFamily: "Be Vietnam Pro, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "13px"
rounded:
  cite: "6px"
  nav: "10px"
  control: "11px"
  card: "14px"
  panel: "18px"
  composer: "20px"
  pill: "999px"
spacing:
  hair: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.jade}"
    textColor: "{colors.on-jade}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0 18px"
    height: "42px"
  button-primary-hover:
    backgroundColor: "{colors.jade-ink}"
    textColor: "{colors.on-jade}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "38px"
  button-secondary-hover:
    backgroundColor: "{colors.jade-mist}"
    textColor: "{colors.jade-ink}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.pill}"
    padding: "0 13px"
    height: "34px"
  chip-hover:
    backgroundColor: "{colors.jade-mist}"
    textColor: "{colors.jade-ink}"
  nav-tab:
    textColor: "{colors.muted}"
    rounded: "{rounded.nav}"
    padding: "0 12px"
    height: "40px"
  nav-tab-active:
    backgroundColor: "{colors.jade-mist}"
    textColor: "{colors.jade-ink}"
  cite-ref:
    backgroundColor: "{colors.jade-mist}"
    textColor: "{colors.jade-ink}"
    rounded: "{rounded.cite}"
    height: "18px"
  verified-seal:
    backgroundColor: "{colors.verified-mist}"
    textColor: "{colors.verified-ink}"
    rounded: "{rounded.pill}"
    padding: "5px 12px 5px 6px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.panel}"
    padding: "24px"
---

# Design System: Enterprise Knowledge AI Agent

## Overview

**Creative North Star: "The Jade Seal"**

The workspace is quiet on purpose. Surfaces are near-white on a faintly sage paper, text is a deep green-black ink, and almost nothing carries colour. The one strong colour, jade, is reserved for what the product promises: an answer whose every claim was checked against its sources. When an answer passes verification a round jade stamp lands beside it, the answer reads like a short cited document in a text serif, and its citations are small jade marks that light up the exact sentence they rely on. Everything else in the interface stays out of the way, so the seal and the evidence are what the eye finds.

Density is calm and exact rather than sparse or crowded. General Chat is the one place to ask questions: a conversation column whose composer carries a "Route to" choice (Auto, Documents only, Sales data). Reports is the report page: a short hero that points to General Chat, then the report generator; tools such as monitoring, access control and invoice review use the same hairline-bordered cards and tables without decoration. A thin layer of frosted glass sits only on the controls that float over the page (the sidebar, the question composer, the monitoring tabs), above soft jade and amber colour fields, so the controls feel lifted while the content they hold stays solid and readable.

The system rejects three looks explicitly: the generic AI-chatbot style (purple or blue gradients, sparkle icons, glowing chat bubbles), busy admin dashboards (KPI walls, heavy shadows, colour-coded everything), and the product's own pre-12-Nov navy-and-blue design.

**Key Characteristics:**
- Ink and jade: one accent family, used only for verification, citations, focus and the primary action.
- Amber means a gap or a partial answer; brick red appears only for errors.
- Two voices: Be Vietnam Pro for the interface, Source Serif 4 for what the documents say (answer text, source passages, example questions). Both render Vietnamese diacritics cleanly. JetBrains Mono only for code.
- Flat, hairline-bordered surfaces; depth comes from glass on the control layer, not from shadows on content.
- Motion only answers an action: the seal settles in, folds open, the theme switches with a circular reveal.
- Two equal themes: light and dark are a token swap, never a separate design.

## Colors

A cool, low-chroma sage neutral world with a single jade accent family and two semantic signals.

### Primary
- **Jade** (`jade`): the primary action button, focus outline, the active navigation marker and the hover state of citation chips. The colour of "verified and trusted".
- **Deep Jade** (`jade-ink`): text and icons on jade-tinted backgrounds (active nav item, citation chips, hovered secondary buttons) and the primary button's hover fill.
- **Jade Mist** (`jade-mist`) and **Jade Line** (`jade-line`): the tinted background and border of anything jade-marked at rest: citation chips, the active nav row, hovered chips, the composer's focus ring.

### Secondary
- **Verified Green** (`verified`, `verified-ink`, `verified-mist`, `verified-line`): the verified-answer seal, completed run statuses, positive ratings and the connected status dot. Shares the jade hue; in dark mode the two families are identical.

### Tertiary
- **Amber** (`amber`, `amber-ink`, `amber-mist`, `amber-line`): gaps and partial answers (the answer mark of a partial answer, analysis caveats, negative ratings, the disconnected status dot). Also tints one of the background colour fields.
- **Brick** (`brick`, `brick-ink`, `brick-mist`, `brick-line`): errors and failed runs, and destructive actions only.

### Neutral
- **Sage Paper** (`sage-paper`): the page background behind everything.
- **Surface** (`surface`): cards, panels, inputs, secondary buttons.
- **Sunk Surface** (`surface-sunk`): table headers, selects inside the composer, hovered table rows, file inputs.
- **Deep Surface** (`surface-deep`): hovered nav rows, inactive tab tracks, skeleton loaders, meter tracks.
- **Hairline** (`hairline`) and **Strong Hairline** (`hairline-strong`): every border; the strong one for dashed drop zones and scrollbars.
- **Ink** (`ink`): headings, answer text, primary text. **Soft Ink** (`ink-soft`): secondary text and button labels. **Muted** (`muted`): supporting text, labels, nav items at rest. **Faint** (`faint`): placeholders and minor notes only.

### Named Rules
**The One Seal Rule.** Jade marks what is verified, cited, focused or the primary action. If an element is none of those, it is not jade.

**The Signal Rule.** Jade means verified, amber means a gap or partial result, red means an error. No colour is used decoratively, and a status always says its meaning in words too.

**The Token Swap Rule.** Every colour comes from a token. Dark mode replaces token values (see the sidecar); it never adds component-specific overrides.

## Typography

**Display Font:** Be Vietnam Pro (with system-ui, sans-serif)
**Body Font:** Be Vietnam Pro (with system-ui, sans-serif)
**Reading Font:** Source Serif 4 (with Georgia, serif), for answer text, source passages and the welcome questions only
**Label/Mono Font:** JetBrains Mono (with ui-monospace, monospace), for code and technical identifiers only

**Character:** a humanist sans designed for Vietnamese carries the interface across five weights (400–650); a text serif carries the evidence, so an answer reads like a short cited document rather than a chat bubble. Hierarchy comes from size and weight, never from uppercase or letter-spacing tricks.

### Hierarchy
- **Display** (600, clamp(28px, 3.2vw, 37px), 1.15, -0.025em): the page hero ("What would you like to know?").
- **Headline** (650, 21px, 1.3, -0.02em): section headings; monitoring uses 24px.
- **Title** (600, 16–17px, 1.3–1.35): card titles, the answer heading, fold titles.
- **Body** (400, 15px, 1.6): interface text; the question field is 16px. Hero copy is limited to 62ch.
- **Answer** (Source Serif 4, 400, 18px, 1.72, at most 64ch): answer text in General Chat, set loose for Vietnamese diacritics; 17px on phones. Source passages use the same serif at 15px.
- **Label** (500, 12.5–13.5px, 1.3–1.4, no tracking, sentence case): eyebrows, chips, table headers, metadata.
- **Figure** (650, 26–30px, tabular numbers): stat and monitoring numbers.

### Named Rules
**The Sentence Case Rule.** No all-caps labels and no letter-spaced eyebrows. Labels are sentence case at 12.5px, weight 500, in Muted.

**The Two Voices Rule.** Be Vietnam Pro is the product speaking (labels, controls, headings, the question); Source Serif 4 is the documents speaking (answers, passages, example questions and the welcome heading). No third family, and the serif never appears on controls or tables.

## Layout

The app is a sidebar workspace: a left sidebar of navigation rows (40px tall, 10px rounded, 19px icons) that collapses without the icons moving, and a content area on Sage Paper. General Chat (the default page after sign-in) is a transcript above a docked composer; Reports (tab id `knowledge`) is a centred single column of at most 880px holding the report generator; tool pages (monitoring, access control, invoice review, processing) use full-width panels with 24px padding. Older content pages keep a 1120px maximum width.

Spacing is small-stepped: 2px between nav rows, 4–8px inside controls and chip rows, 12–16px inside cards, 22–30px between page blocks (for example 30px above the answer panel). Tables use tabular numbers and hairline rules.

Responsive behaviour: the main breakpoint is 780px, where the sidebar becomes a bar and the glass rim moves to its bottom edge; further adjustments happen at 740px, 600px and 440px. The phone layout is tested at 390px width.

### Named Rules
**The Question-First Rule.** In General Chat each question becomes the heading of its answer (600, 21px), and the composer is the most elevated element on the page; supporting statistics shrink to one inline line, and nothing else floats.

**The One-Chat Rule.** There is one chat. Choosing documents or sales data is a "Route to" setting in that chat, never a second chat box on another page. On phones the composer wraps: the text box takes the full width (at least 56px tall) and the Route to choice and Send sit below it.

## Elevation & Depth

Content is flat. Cards, panels, tables and citations sit on hairline borders with at most a whisper shadow, and in dark mode content shadows are removed entirely. Depth belongs to the control layer: the sidebar, the question composer, the general-chat composer and the monitoring tabs are frosted glass (22px blur, 175% saturation) over three soft radial colour fields (two jade, one amber) fixed behind the page, with an inset rim highlight and a top sheen. The primary button carries a small glossy lens. When the reader asks for reduced transparency, or the browser lacks backdrop blur, all glass becomes solid Surface and the colour fields disappear.

### Shadow Vocabulary
- **Whisper** (`box-shadow: 0 1px 2px rgba(20,33,29,.04)`): panels and the login card at rest; none in dark mode.
- **Float** (`box-shadow: 0 10px 30px -12px rgba(20,33,29,.22), 0 2px 6px rgba(20,33,29,.05)`): the question composer.
- **Glass** (inset rim plus a soft drop; exact value in the sidecar): every glass control.
- **Focus ring** (`box-shadow: 0 0 0 3px` Jade Mist, 4px on the composer): focused fields and highlighted citations.

### Named Rules
**The Solid Content Rule.** Glass is only for navigation and controls. Answers, citations, tables and forms are always solid and fully opaque.

## Shapes

Soft, consistent corners that grow with the size of the container: 6px for inline citation chips, 10px for nav rows and small toggles, 11px for buttons and fields, 14px for cards, citations and tables, 18px for panels, 20px for the question composer, and full pills for quick chips, badges, statuses and the verified seal. Borders are single 1px hairlines; dashed borders mark drop zones only. Circles appear only for status dots and the seal's check mark.

## Components

The feel is calm and exact: soft corners, hairlines, no ornament; precision comes from alignment and colour discipline.

### Buttons
- **Shape:** gently rounded (11px).
- **Primary:** Jade fill, white label (600, 14px), 42px tall, 18px side padding, with a subtle glossy lens highlight. Used for the main action of a view (Ask, Generate report).
- **Hover / Focus:** fill deepens to Deep Jade; a 2px Jade focus outline offset by 2px; every button scales to 0.97 while pressed. Transitions run 0.12–0.16s on the standard ease.
- **Secondary:** Surface fill, hairline border, Soft Ink label (500, 13.5px), 38px tall; on hover it takes Jade Mist fill, Jade Line border and Deep Jade text. "New conversation" is a ghost variant with a transparent border.
- **Disabled:** 55% opacity with a progress cursor while a request runs.

### Chips
- **Quick prompts:** 34px pills with a hairline border, Surface fill and Soft Ink text; hover tints them jade.
- **Badges and statuses:** small pills; completed runs use Verified Mist and Verified Ink, failed runs use Brick Mist and Brick Ink, ratings use Verified or Amber.

### Cards / Containers
- **Corner Style:** 14px for cards and citations, 18px for panels.
- **Background:** Surface on Sage Paper.
- **Shadow Strategy:** flat (see Elevation & Depth).
- **Border:** 1px Hairline; a highlighted citation switches to a Jade border with a 3px Jade Mist ring.
- **Internal Padding:** 16–24px.

### Inputs / Fields
- **Style:** Surface fill, 1px Hairline border, 11px corners, 14px text, Faint placeholders; selects use a custom chevron.
- **Focus:** the border turns Jade and a 3px Jade Mist ring appears; no outline glow beyond that.
- **File inputs:** a dashed Strong Hairline drop zone on Sunk Surface that tints jade on hover.

### Navigation
- **Sidebar rows:** 40px tall, 10px corners, Muted label (500, 14px) with a 19px line icon. Hover fills Deep Surface; the active row takes Jade Mist with Deep Jade text (600) and a 3px jade marker bar that grows in from its centre.
- **Monitoring sub-tabs:** a glass segmented control (4px inset track, 34px tabs, 9px corners); the selected tab becomes a lighter glass chip.
- **Width:** 272px by default; dragging its right edge (or arrow keys on the focused edge) resizes it between 220px and 420px, a 2px Jade Line shows while dragging, a double-click resets it, and the width is kept per browser. Collapsed, it is 76px and cannot be dragged.
- **Logo:** a faceless girl with very long, straight, pale-gold hair swept back from a side part, one side tucked behind the ear with a small dark hoop, wearing a dark brown robe with green lining over a grey V-neck and a green-and-silver striped tie, on a Jade Mist tile with a Jade Line border. No house crest or name (that is Warner Bros' trademark). Used in the sidebar and on the login page.
- **Phone:** below 780px the sidebar becomes a bar with its glass rim on the bottom edge.

### Tool Pages
Upload, Invoice Review, Knowledge Management, Access Control, Monitoring and Processing share one frame: the heading (650, 26px), one Muted description of at most 72ch and the page's action button sit on the page itself, with no panel around them; status lines are left-aligned. Content lives in hairline-bordered Surface lists: invoices and knowledge files are hairline rows in one surface, not separate cards. Knowledge rows have a fixed 232px action column of equal-width buttons, the safe action on top. Status labels are small tinted pills with a dot (Available to AI: Verified; Processing failed or No passages yet: Amber; Removed: neutral; Still processing pulses). Access Control is a real matrix (roles down, permissions across, a Verified tick where allowed); on phones it scrolls sideways with the role column pinned. Monitoring shows its figures in one strip divided by hairlines.

### Confirmation Dialog
Every confirmation uses the app's own modal instead of the browser's: Surface, 18px corners, a soft deep shadow, a blurred ink backdrop, and a 0.18s fade and scale in. A title that asks the question, one Muted sentence on the consequence, then Cancel and a button that names the action ("Reject invoice", "Delete permanently"). Destructive actions use a solid Brick button and put the initial focus on Cancel; Esc or a click outside cancels.

### Dropdown List
Where the browser supports customisable selects (current Chrome and Edge), the open list is a Surface sheet with 12px corners and the floating shadow; options are 36px rows, hover fills Sunk Surface, and the chosen option is Jade Mist with Deep Jade text and a Jade tick. It fades in over 0.16s. Other browsers keep their native list.

### Verified Answer Seal (signature)
A round stamp, 54px, in the left gutter beside a verified answer: a Verified ring on Surface, a dashed inner ring on Verified Mist, and a check that draws itself in. It lands once with a 0.6s stamp (scale down from 1.3 while turning to its resting -8°). Beside it a plain Verified Ink line says "Every claim checked against its cited source · N claims"; the words carry the meaning, the stamp is decoration (aria-hidden). On phones the stamp sits above the answer at 44px. Partial, withheld and not-covered answers never get the stamp; they keep their Amber outcome pill.

### Citation Mark
Inline source references in answer text (S1, S2 …) are small raised marks (Deep Jade, 600, 12.5px, superscript) that hug the word before them and keep the following punctuation on the same line. Hover or focus fills the mark with Jade and marks the matching sentence of the cited passage with a soft jade highlight; clicking scrolls to and opens that source.

### Answer Outcome Pill
The seal's siblings, in the same position directly under the answer title and with the same pill anatomy, in Amber: "Withheld: <reason from the claim check>" (exclamation glyph), "Not covered by the documents you can access" and "Partial answer: some parts are not covered" (dash glyph). The title changes to "Answer withheld" or "Not in your documents". Withheld and not-covered answers carry a secondary "Rephrase the question" button that puts the question back in the composer. A withheld answer is the check doing its job, so it is never styled as an error.

### Answer Progress Stepper
Shown while an answer is prepared (10–20 s): a solid card with a steady headline ("Working on your answer"), elapsed seconds with "usually 10–20 s" (or "taking longer than usual" after 25 s), a Stop button, and a fixed list of plain-language steps: choosing the agent, searching in Vietnamese and English, ranking passages, querying sales data (only when used), writing a cited answer, checking every claim. Markers are 18px circles: hairline when waiting, a pulsing Jade dot when active, a Verified tick when done (it settles in once), dashed when skipped, Brick with a cross when failed. Only the step name is announced to screen readers; the clock and list stay silent. Stopping leaves a muted "You stopped this answer" note.

### Answer Anatomy
Top to bottom: title, outcome (seal or pill), answer text with citation chips, "Sources (n)", then Run details and token usage folded shut, then the rating and copy bar. Copy is left out when the answer was withheld or not covered.

### Source Footnote
Under a full-width Ink rule, "Sources (n)" lists each source as a footnote: the id in the gutter (Deep Jade, 600), the file name and page on one line, then the passage in the serif, clamped to two lines with a "Show full passage" text button (removed when the passage already fits). Footnotes are separated by hairlines; there are no cards. Publisher and evidence class appear only when the data has them.

### Welcome Questions
An empty chat shows the live document count ("42 documents and the sales data are ready to ask") and four real questions, one per area (Purchasing, Business travel, Inventory, Sales data): the area label in Muted on the left, the Vietnamese question in the serif with its English gist beneath. Rows are hairline-separated and tint Jade Mist on hover; choosing one asks it.

### Service Notice
When search statistics cannot load, the header status reads "Search unavailable" and a whole tinted Amber notice appears at the top of the chat with a Retry button. It is an alert, not a modal, and it never blocks typing.

### Undo Strip
"New conversation" clears the chat at once and shows a slim strip with an Undo button for 8 seconds; Undo restores the previous conversation. There is no confirm dialog.

## Do's and Don'ts

### Do:
- **Do** reserve Jade for verified answers, citations, focus and the single primary action of a view.
- **Do** pair every status colour with words ("Every claim checked", "Partial answer", "Failed").
- **Do** take every colour from a token so dark mode stays a pure token swap.
- **Do** keep content solid and put glass only on the sidebar, composers and tab controls, with a solid fallback for reduced transparency.
- **Do** animate only in response to an action (seal, folds, theme reveal, nav marker, rows settling in when a tool page opens but not when a filter re-renders it, access ticks, monitoring figures counting up, agent bars growing, the invoice draft fading in when another is chosen, dialogs and dropdowns fading in) and switch all motion off for reduced motion.
- **Do** use tabular numbers (`font-variant-numeric: tabular-nums`) for every figure in stats and tables.
- **Do** draw monitoring bars in Muted ink; a bar is a quantity, not a verdict, so it never takes Jade.
- **Do** show people the plain names of roles, permissions, agents and checks ("Finance analyst", "Ask documents"), never internal ids.

### Don't:
- **Don't** use purple or blue gradients, sparkle icons or glowing chat bubbles; this is not a generic AI-chatbot look.
- **Don't** build KPI walls, add heavy shadows or colour-code everything; it is not a busy admin dashboard.
- **Don't** bring back the old navy (#14283d) and blue (#2369d8) palette; those names survive only as aliases to the jade tokens.
- **Don't** use all-caps labels, letter-spaced eyebrows or decorative numbering.
- **Don't** use red for anything but errors and destructive actions, or amber for anything but gaps and partial results.
- **Don't** set essential text in Faint; it is for placeholders and minor notes only (it holds 4.5:1 on Surface, Sage Paper and Sunk Surface, but not on Deep Surface).
- **Don't** put a coloured stripe on one side of a card, callout or note; notes are whole tinted boxes with one hairline border. A quote bar on a real blockquote is the one exception.
- **Don't** use the browser's alert or confirm boxes; use the Confirmation Dialog.
- **Don't** put a small label or eyebrow above a page heading; the heading and its description carry the page.
- **Don't** set text below 12.5px (12px for code); the older stylesheet's 9–11px sizes are overridden by a floor in redesign.css.
