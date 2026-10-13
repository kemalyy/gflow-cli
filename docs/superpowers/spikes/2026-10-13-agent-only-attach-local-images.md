# The agent-only composer takes local images as ingredient chips from its own add menu

**Date:** 2026-10-13 · **Issue:** #799 · **Cost:** 0 credits. Uploads only, plus one i2i image (daily quota). **No video was submitted.**
**Probe:** [`scripts/dev/spike_agent_only_attach.py`](../../../scripts/dev/spike_agent_only_attach.py) (`--open-add`, `--upload`, `--copies`, `--click-chip`, `--dry-video`)
**Captures:** `scripts/dev/_spike_out/spike_agent_only_attach_20261013_*.json` + screenshots (gitignored)
**Account:** an AI Pro account served `flow.google.com`, UI locale **tr**, on the agent-only composer (no classic composer, no agent-mode chip).

## Question

The [2026-09-15 spike](2026-09-15-agent-only-composer-drive-surface.md) left i2v and r2v unmeasured. How
does the agent-only composer take a local image, and how are a start frame, an end frame and
references expressed?

## What was observed

| Role | Anchor (structural, locale-free) | Notes |
|---|---|---|
| attach trigger | `flow-creative-agent-prompt-box button.add-menu-trigger` (ligature `add`; `close` while open) | inside the prompt box (`flow-add-menu` → `flow-base-prompt-box`) |
| picker | `flow-add-menu-popover-content` | the same component the classic `@` mention opens. It has a side nav (`mat-list-item[role=tab]`: all / images / videos / voices / characters / avatars / uploads), a `input.search-input`, and `button.asset-item[role=option]` options |
| upload | `flow-add-menu-popover-content button.sidebar-upload-btn` (ligature `upload`) | opens a file chooser, which takes `multiple=True`. The app's own `maseQ` answers `[media_id, project_id, …]`, as on the classic composer |
| commit | `button.detail-add-to-prompt-btn` | **an option click only selects** (`asset-item-active`), and this button commits it. The popover then closes |
| attached image | `flow-ingredient-bar` → `flow-ingredient-chip` → `flow-image-ingredient-chip` → `button.chip-container` → `img.chip-image` | the img src is `flow-content.google/image/<uuid>`, and **that uuid equals the `maseQ` media id** (3/3 uploads) |

Other findings:

- **The popover's active item is NOT the new upload.** On the first run, clicking "Add to prompt"
  right after uploading attached the asset that was already active in the list (an older image),
  not the upload. The upload has to be selected by its own option, matched on the run-unique
  display name, and then committed.
- **Chips are added in attach order** (two uploads → two chips, first-attached first), outside
  the ProseMirror editor. Text typed into the editor leaves them alone.
- **A chip carries no role.** It has no `data-reference-type`, no Start/End slot, and no menu.
  Clicking a chip opens `flow-image-ingredient-preview` (just a preview), and **clicking its
  corner hit the hover `cancel` overlay and removed the chip.** The driver never clicks a chip.
- **An upload joins the project grid as an image tile** (seen in the dry-run screenshot). The
  result scan would count it as new media unless it is excluded.
- Drafts did not survive page loads: each fresh load started with an empty chip bar.
- The page's toolbar `+` (outside the prompt box) also offers `upload`, but that upload does not
  open the picker, so the driver uses the box's own menu.

## Live i2i (1 image, 0 credits)

`gflow image i2i "<prompt>" --ref <girl.jpg> --aspect 9:16 --project <id>` ran with gate approval
disabled by a harness. It uploaded, attached (the chip uuid equalled the `maseQ` id), and submitted
`Make me a picture of … in a 9:16 aspect ratio, using the attached image as a reference.`. No
credit gate appeared. One new 768×1376 image arrived ~30 s after submit, and the agent replied
that it had used "your reference photo to keep her appearance consistent". The face, brows,
eyes and ponytail match the reference, and the clothes changed as asked.

## Video: dry run up to submit (never submitted)

With `--dry-video i2v-end` and `--dry-video r2v`, the driver's own `attach_images` ran,
followed by the composed directive. Two chips were bound, their uuids equalled the two `maseQ`
ids in order, and the directive was typed as:

- i2v (start + end): `… using the first attached image as its first frame and the second attached image as its last frame.`
- r2v: `… using the 2 attached images as references.`

`gates=0` and submit was present. **Whether the agent honours those roles is a hypothesis.**
Chips carry no role in the DOM, so the request text is the only lever. It holds until a video is
submitted, which costs credits and was not authorised here.

## What was NOT measured

- **Live video submit from attached images** (i2v, i2v with an end frame, r2v): credits.
- Whether the agent uses a start frame as the literal first frame or only as a reference.
- More than 2 chips. The chip-bar maximum is unknown.
- The one-time "rights to use this image" upload dialog. This account had uploaded before. The
  shared upload code still detects it and refuses (exit 27).
- Repeatability: N=1 per mode, one account.
