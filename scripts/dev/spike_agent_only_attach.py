r"""How does #799's agent-only composer take a LOCAL image (i2i, i2v start/end, r2v)?

Cost: every phase is $0 — navigation, DOM reads, opening menus, and (``--upload``) one
image upload into the project's library (an upload is not a generation; nothing is
billed). **Nothing is ever submitted**: the probe never clicks the generate button and
never answers a credit gate. ``--type`` only types a directive into the editor and
reads it back, then clears it.

    python scripts/dev/spike_agent_only_attach.py --profile <name> --project <id> \
        [--open-add] [--upload <image>] [--type "<directive>"]

Pre-registered readings (written before the first run):

| Observation | Reading |
|---|---|
| a button with ligature `add` / `attach_file` / `add_photo_alternate` inside the agent prompt box | the agent composer has its own attach affordance — inventory its menu |
| only the toolbar `+` (outside the prompt box) offers `upload` | uploads go to the library; the agent must be pointed at them some other way (@-mention or chip) |
| after an upload, an `img` / chip appears INSIDE `flow-creative-agent-prompt-box` | attaching is a chat attachment, sent with the directive |
| typing `@` in ProseMirror opens `flow-add-menu-popover-content` | mentions work in the agent editor as in the classic composer |
| no attach affordance and `@` opens nothing | NOT evidence the agent cannot take images — record and escalate to the HAR harness |
"""

# ruff: noqa: E501 - inline JS and the readings table; wrapping them hides their shape

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _spike_common import (  # noqa: E402, isort: skip
    build_client,
    default_out_path,
    resolve_profile_dir,
    step,
)

#: Every visible control + file input, with its ligatures and custom-tag ancestry, plus
#: whatever sits inside the agent prompt box (attachments render there if anywhere).
_INVENTORY_JS = r"""
() => {
  const visible = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const ligs = (el) => [...el.querySelectorAll('mat-icon, i')].map(i => (i.textContent || '').trim()).filter(Boolean);
  const chain = (el) => {
    const out = [];
    for (let n = el; n && n !== document.body && out.length < 7; n = n.parentElement)
      if (n.tagName.includes('-')) out.push(n.tagName.toLowerCase());
    return out;
  };
  const controls = [...document.querySelectorAll(
    "button, [role=menuitem], [role=option], [role=tab], [role=radio], input, [contenteditable=true]"
  )].filter(e => visible(e) || e.type === 'file').map(e => ({
    tag: e.tagName.toLowerCase(), type: e.getAttribute('type'), accept: e.getAttribute('accept'),
    multiple: e.hasAttribute('multiple'), role: e.getAttribute('role'),
    aria: e.getAttribute('aria-label'), ligatures: ligs(e),
    classes: [...e.classList].filter(c => !c.startsWith('mat-') && !c.startsWith('mdc-')).slice(0, 5),
    text: (e.innerText || '').trim().slice(0, 40), chain: chain(e), visible: visible(e),
  }));
  const box = document.querySelector('flow-creative-agent-prompt-box') || document.querySelector('flow-base-prompt-box');
  const outline = box ? [...box.querySelectorAll('*')].filter(e => e.tagName.includes('-') || e.tagName === 'IMG' || e.matches('[class*=chip],[class*=attach],[class*=thumb],[data-reference-type]')).map(e => ({
    tag: e.tagName.toLowerCase(), classes: [...e.classList].slice(0, 5),
    src: (e.getAttribute('src') || '').slice(0, 120), ref: e.getAttribute('data-reference-type'),
    media: e.getAttribute('data-media-id'), text: (e.innerText || '').trim().slice(0, 60),
  })) : null;
  return {
    url: location.href, lang: document.documentElement.lang,
    prompt_box: box ? box.tagName.toLowerCase() : null,
    editor_html: (document.querySelector('div.ProseMirror') || {}).innerHTML?.slice(0, 1500) || null,
    file_inputs: document.querySelectorAll('input[type=file]').length,
    overlays: [...document.querySelectorAll('.cdk-overlay-container *')].filter(e => e.tagName.includes('-') && visible(e)).map(e => e.tagName.toLowerCase()).slice(0, 40),
    controls, outline,
  };
}
"""

#: The classic composer's toolbar `+` — the add affordance OUTSIDE any prompt box.
TOOLBAR_ADD = (
    "xpath=//button[.//mat-icon[normalize-space()='add']]"
    "[not(ancestor::flow-prompt-box)][not(ancestor::flow-creative-agent-prompt-box)]"
)
BOX_ADD = "flow-creative-agent-prompt-box button.add-menu-trigger"
PICKER = "flow-add-menu-popover-content"
CHIP = "flow-creative-agent-prompt-box button.chip-container"
_CHIPS_JS = r"""
() => [...document.querySelectorAll('flow-creative-agent-prompt-box button.chip-container')].map(c => ({
  html: c.outerHTML.slice(0, 900),
  src: (c.querySelector('img') || {}).src || '',
}))
"""


async def _snap(page: Any, tag: str, findings: dict[str, Any]) -> dict[str, Any]:
    inv = await page.evaluate(_INVENTORY_JS)
    shot = default_out_path(f"spike_agent_only_attach_{tag}", ".png")
    await page.screenshot(path=str(shot))
    inv["screenshot"] = shot.name
    findings[tag] = inv
    box = [c for c in inv["controls"] if any("prompt-box" in t for t in c["chain"])]
    step(
        tag,
        f"controls={len(inv['controls'])} file_inputs={inv['file_inputs']} "
        f"box={inv['prompt_box']} overlays={inv['overlays'][:6]}",
    )
    step("  editor", str(inv["editor_html"])[:600])
    for o in inv["outline"] or []:
        if o["tag"] == "img" or o["ref"] or o["media"]:
            step("  outline", json.dumps(o)[:300])
    for c in box:
        step("  box", f"{c['tag']} lig={c['ligatures']} cls={c['classes']} aria={c['aria']!r}")
    for c in inv["controls"]:
        if c["tag"] == "input" and c["type"] == "file":
            step("  file", f"accept={c['accept']} multiple={c['multiple']} chain={c['chain']}")
        if c["role"] in ("menuitem", "option"):
            step("  item", f"lig={c['ligatures']} cls={c['classes']} text={c['text']!r}")
    return inv


async def _rpc_tap(page: Any, findings: dict[str, Any]) -> None:
    calls: list[str] = findings.setdefault("rpcids", [])

    def on_request(request: Any) -> None:
        url = str(request.url)
        if "batchexecute" in url and "rpcids=" in url:
            calls.append(url.split("rpcids=", 1)[1].split("&", 1)[0])

    page.on("request", on_request)

    async def on_response(response: Any) -> None:
        url = str(response.url)
        if "rpcids=maseQ" in url:
            import re

            body = await response.text()
            ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", body)
            findings.setdefault("maseQ", []).append({"status": response.status, "ids": ids[:4]})
            step("maseQ", f"status={response.status} ids={ids[:2]}")

    page.on("response", on_response)


async def _dry_video(page: Any, args: Any, findings: dict[str, Any]) -> None:
    """The driver's own attach + directive, stopped before submit. $0: uploads only."""
    from gflow_cli.api.transports import agent_only_composer as aoc

    if args.upload is None:
        raise SystemExit("--dry-video needs --upload <image>")
    composer = aoc.AgentOnlyComposer()
    n = 1 if args.dry_video == "i2v" else 2
    attached_as = {"i2v": "start_frame", "i2v-end": "start_end_frames", "r2v": "references"}
    ids = await composer.attach_images(page, args.project, (args.upload,) * n)
    directive = aoc.compose_video_directive(
        "the girl turns her head and smiles",
        8,
        "9:16",
        attached=attached_as[args.dry_video],  # type: ignore[arg-type]
        images=len(ids),
    )
    editor = page.locator(aoc.EDITOR).last
    await editor.click(timeout=5_000)
    await page.keyboard.insert_text(directive)
    await page.wait_for_timeout(1_000)
    findings["dry_video"] = {
        "mode": args.dry_video,
        "attached": list(ids),
        "chips": await composer.chip_uuids(page),
        "directive": directive,
        "editor": await editor.inner_text(),
        "submit_present": await page.locator(aoc.SUBMIT).count(),
        "gates": await page.locator(aoc.LIVE_GATE).count(),
    }
    await _snap(page, f"dry_{args.dry_video}", findings)
    step("dry", json.dumps(findings["dry_video"]))
    # NEVER submitted: the page closes with the draft in it.


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--open-add", action="store_true", help="open each add menu, then Escape")
    ap.add_argument("--upload", type=Path, help="upload this image through the box's attach")
    ap.add_argument("--copies", type=int, default=1, help="upload+attach this many times")
    ap.add_argument("--click-chip", action="store_true", help="click the first chip body")
    ap.add_argument("--type", dest="directive", help="type this into the editor, read, clear")
    ap.add_argument("--mention", help="type '@' + this into the editor, inventory the picker")
    ap.add_argument(
        "--dry-video",
        choices=("i2v", "i2v-end", "r2v"),
        help="drive the REAL driver's attach + directive for a video, read it back, never submit",
    )
    ap.add_argument("--hold-s", type=float, default=0.0, help="keep the page open for a look")
    args = ap.parse_args()

    findings: dict[str, Any] = {"project": args.project, "question": "agent-only attach path"}
    url = f"https://flow.google.com/project/{args.project}"
    async with build_client(resolve_profile_dir(args.profile)) as client:
        page = await client._context.new_page()  # noqa: SLF001 - spike reads the live context
        await _rpc_tap(page, findings)
        step("goto", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(9_000)
        await _snap(page, "inventory", findings)

        if args.open_add:
            for name, sel in (("box_add", BOX_ADD), ("toolbar_add", TOOLBAR_ADD)):
                loc = page.locator(sel)
                findings[f"{name}_count"] = await loc.count()
                if not await loc.count():
                    step(name, "absent")
                    continue
                await loc.last.click(timeout=5_000)
                await page.wait_for_timeout(2_000)
                await _snap(page, f"{name}_open", findings)
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1_000)

        if args.upload and not args.dry_video:
            # Measured on the first run: the box's `add` opens `flow-add-menu-popover-content`
            # whose side nav carries `button.sidebar-upload-btn` (ligature `upload`).
            await page.locator(BOX_ADD).last.click(timeout=5_000)
            await page.wait_for_timeout(1_500)
            item = page.locator(f"{PICKER} button.sidebar-upload-btn").first
            async with page.expect_file_chooser(timeout=8_000) as fc:
                await item.click(timeout=4_000)
            chooser = await fc.value
            findings["chooser_multiple"] = chooser.is_multiple()
            for n in range(args.copies):
                if n:
                    await page.locator(BOX_ADD).last.click(timeout=5_000)
                    await page.wait_for_timeout(1_500)
                    async with page.expect_file_chooser(timeout=8_000) as fc:
                        await item.click(timeout=4_000)
                    chooser = await fc.value
                # A run-unique display name, as the classic driver uploads under.
                name = f"spike{int(time.time())}_{n}_{args.upload.name}"
                await chooser.set_files(
                    {"name": name, "mimeType": "image/jpeg", "buffer": args.upload.read_bytes()}
                )
                await page.wait_for_timeout(3_000)
                await _snap(page, f"after_upload_{n}", findings)
                # Pick the uploaded option by its display name, then "Add to prompt".
                option = page.locator(
                    f"{PICKER} button.asset-item[role=option]", has_text=name[:20]
                )
                for _ in range(20):
                    if (
                        await option.count()
                        and not await option.first.locator("mat-progress-spinner, .loading").count()
                    ):
                        break
                    await page.wait_for_timeout(1_000)
                await page.wait_for_timeout(4_000)
                await option.first.click(timeout=5_000)
                await page.wait_for_timeout(2_500)
                await _snap(page, f"option_clicked_{n}", findings)
                confirm = page.locator(f"{PICKER} button.detail-add-to-prompt-btn")
                if await confirm.count() and await confirm.first.is_visible():
                    await confirm.first.click(timeout=4_000)
                    await page.wait_for_timeout(2_500)
                await _snap(page, f"after_add_to_prompt_{n}", findings)
            findings["chips"] = await page.evaluate(_CHIPS_JS)
            step("chips", json.dumps(findings["chips"])[:800])
            if args.click_chip:
                await page.locator(CHIP).first.click(timeout=4_000, position={"x": 8, "y": 8})
                await page.wait_for_timeout(2_000)
                await _snap(page, "chip_clicked", findings)
                await page.keyboard.press("Escape")

        if args.mention is not None:
            await page.locator("div.ProseMirror").last.click(timeout=5_000)
            await page.keyboard.type("@", delay=120)
            await page.wait_for_timeout(2_200)
            await page.keyboard.type(args.mention, delay=100)
            await page.wait_for_timeout(3_000)
            await _snap(page, "mention_open", findings)
            await page.keyboard.press("Escape")

        if args.directive:
            await page.locator("div.ProseMirror").last.click(timeout=5_000)
            await page.keyboard.press("End")
            await page.keyboard.insert_text(args.directive)
            await page.wait_for_timeout(1_000)
            await _snap(page, "typed", findings)

        if args.dry_video:
            await _dry_video(page, args, findings)

        if args.hold_s > 0:
            step("hold", f"{args.hold_s:.0f}s — NOTHING will be submitted")
            await page.wait_for_timeout(args.hold_s * 1000)

    out = default_out_path("spike_agent_only_attach")
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    step("done", f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
