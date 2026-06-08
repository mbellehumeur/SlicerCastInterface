"""Build animated binary-transfer SVGs from binary-file-transfer.svg."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
SRC = HERE / "binary-file-transfer.svg"
SRC_FALLBACK = HERE / "binary-file-transfer-animated.svg"
DUR = "30s"

FILE_STACK_INNER = """
      <rect x="0" y="12" width="28" height="36" rx="4" fill="#dbeafe" stroke="#2457d6" stroke-width="2"/>
      <rect x="24" y="6" width="28" height="36" rx="4" fill="#dbeafe" stroke="#2457d6" stroke-width="2"/>
      <rect x="48" y="0" width="28" height="36" rx="4" fill="#dbeafe" stroke="#2457d6" stroke-width="2"/>
"""

DIRECTIONS: Dict[str, Dict[str, Any]] = {
    "id_to_rs": {
        "out": HERE / "binary-file-transfer-animated.svg",
        "title": "Binary file transfer (animated)",
        "desc": (
            "Files move with POST from Image Display; hub stores payloadIds; "
            "WebSocket notify; GET file bytes; payload TTL expires and hub clears memory."
        ),
        "id_subtitle": ("View and interact", "with medical images"),
        "rs_subtitle": ("e.g. TotalSegmentator", "GETs bytes when ready"),
        "flow_post": "M345 350 L545 350",
        "flow_ws": "M655 350 L835 350",
        "flow_get": "M655 340 L835 340",
        "step1": (
            "Step 1: Image Display publishes an event with Content-Type: multipart/related",
            "and one binary part per file.",
            "The context data contains the manifest of each file.",
        ),
        "step3_ws": "Cast Hub → Resource Server over WebSocket",
        "step4": (
            "Step 4: GET requests — Resource Server fetches the files it needs",
            "All three files fetched — bytes accumulate in files[].data",
        ),
        "accum_tray_x": 858,
        "accum_center_x": 980,
        "upload_start": (182, 248),
        "upload_end": (562, 248),
        "post_start": (220, 320),
        "post_end": (600, 320),
        "ws_start": (600, 360),
        "ws_end": (980, 360),
        "get_targets": [(900, 480), (940, 480), (980, 480)],
        "accum_landings": [(908, 542), (952, 542), (996, 542)],
    },
    "rs_to_id": {
        "out": HERE / "binary-file-transfer-animated-rs-to-id.svg",
        "title": "Binary file transfer — result to viewer (animated)",
        "desc": (
            "Resource Server POSTs result files; hub stores payloadIds; "
            "WebSocket notify to Image Display; GET file bytes; payload TTL expires."
        ),
        "id_subtitle": ("View and interact", "GETs bytes when ready"),
        "rs_subtitle": ("e.g. TotalSegmentator", "POSTs result when ready"),
        "flow_post": "M835 350 L655 350",
        "flow_ws": "M545 350 L345 350",
        "flow_get": "M545 340 L345 340",
        "step1": (
            "Step 1: Resource Server publishes an event with Content-Type: multipart/related",
            "and one binary part per file (e.g. segmentation result).",
            "The context data contains the manifest of each file.",
        ),
        "step3_ws": "Cast Hub → Image Display over WebSocket",
        "step4": (
            "Step 4: GET requests — Image Display fetches the files it needs",
            "All three files fetched — bytes accumulate in files[].data",
        ),
        "accum_tray_x": 98,
        "accum_center_x": 220,
        "upload_start": (868, 248),
        "upload_end": (562, 248),
        "post_start": (980, 320),
        "post_end": (600, 320),
        "ws_start": (600, 360),
        "ws_end": (220, 360),
        "get_targets": [(300, 480), (260, 480), (220, 480)],
        "accum_landings": [(148, 542), (192, 542), (236, 542)],
    },
}


def _anim_style(cfg: Dict[str, Any]) -> str:
    usx, usy = cfg["upload_start"]
    uex, uey = cfg["upload_end"]
    psx, psy = cfg["post_start"]
    pex, pey = cfg["post_end"]
    wsx, wsy = cfg["ws_start"]
    wex, wey = cfg["ws_end"]
    g1x, g1y = cfg["get_targets"][0]
    g2x, g2y = cfg["get_targets"][1]
    g3x, g3y = cfg["get_targets"][2]
    a1x, a1y = cfg["accum_landings"][0]
    a2x, a2y = cfg["accum_landings"][1]
    a3x, a3y = cfg["accum_landings"][2]

    return f"""
      #castHubGraphic {{ transform-origin: 600px 340px; animation: hubPulse {DUR} infinite; }}
      @keyframes hubPulse {{
        0%, 18% {{ transform: scale(1); }}
        22%, 32% {{ transform: scale(1.07); }}
        36%, 100% {{ transform: scale(1); }}
      }}
      #step1Caption {{ animation: step1Caption {DUR} infinite; }}
      @keyframes step1Caption {{
        0%, 3% {{ opacity: 0; }}
        5%, 20% {{ opacity: 1; }}
        22%, 100% {{ opacity: 0; }}
      }}
      #step2Caption {{ animation: step2Caption {DUR} infinite; }}
      @keyframes step2Caption {{
        0%, 20% {{ opacity: 0; }}
        22%, 32% {{ opacity: 1; }}
        34%, 100% {{ opacity: 0; }}
      }}
      #step3Caption {{ animation: step3Caption {DUR} infinite; }}
      @keyframes step3Caption {{
        0%, 32% {{ opacity: 0; }}
        34%, 42% {{ opacity: 1; }}
        44%, 100% {{ opacity: 0; }}
      }}
      #step4Caption {{ animation: step4Caption {DUR} infinite; }}
      @keyframes step4Caption {{
        0%, 42% {{ opacity: 0; }}
        44%, 72% {{ opacity: 1; }}
        74%, 100% {{ opacity: 0; }}
      }}
      #step5Caption {{ animation: step5Caption {DUR} infinite; }}
      @keyframes step5Caption {{
        0%, 72% {{ opacity: 0; }}
        74%, 88% {{ opacity: 1; }}
        90%, 100% {{ opacity: 0; }}
      }}
      #flowLinePost {{ animation: flowLinePost {DUR} infinite; }}
      @keyframes flowLinePost {{
        0%, 3% {{ stroke: #cbd5e1; opacity: 0.5; }}
        5%, 22% {{ stroke: #2457d6; opacity: 1; }}
        24%, 100% {{ stroke: #cbd5e1; opacity: 0.5; }}
      }}
      #flowLineWs {{ animation: flowLineWs {DUR} infinite; }}
      @keyframes flowLineWs {{
        0%, 32% {{ stroke: #cbd5e1; opacity: 0.5; }}
        34%, 44% {{ stroke: #2457d6; opacity: 1; }}
        46%, 100% {{ stroke: #cbd5e1; opacity: 0.5; }}
      }}
      #flowLineGet {{ animation: flowLineGet {DUR} infinite; }}
      @keyframes flowLineGet {{
        0%, 42% {{ stroke: #cbd5e1; opacity: 0.5; }}
        44%, 72% {{ stroke: #1f9d55; opacity: 1; }}
        74%, 100% {{ stroke: #cbd5e1; opacity: 0.5; }}
      }}
      .packetStowPost {{ opacity: 0; animation: packetStowPost {DUR} infinite; }}
      @keyframes packetStowPost {{
        0%, 3% {{ opacity: 0; transform: translate({psx}px, {psy}px); }}
        5% {{ opacity: 1; transform: translate({psx}px, {psy}px); }}
        18% {{ opacity: 1; transform: translate({pex}px, {pey}px); }}
        21%, 100% {{ opacity: 0; transform: translate({pex}px, {pey}px); }}
      }}
      #uploadFileStack {{
        transform-origin: 0 0;
        animation: uploadFileStack {DUR} infinite;
      }}
      @keyframes uploadFileStack {{
        0%, 3% {{ opacity: 0; transform: translate({usx}px, {usy}px); }}
        5% {{ opacity: 1; transform: translate({usx}px, {usy}px); }}
        18% {{ opacity: 1; transform: translate({uex}px, {uey}px); }}
        21%, 100% {{ opacity: 0; transform: translate({uex}px, {uey}px); }}
      }}
      #hubPayloadStack {{
        transform-origin: 600px 260px;
        animation: hubPayloadStack {DUR} infinite;
      }}
      @keyframes hubPayloadStack {{
        0%, 20% {{ opacity: 0; transform: scale(0.92); }}
        22%, 73% {{ opacity: 1; transform: scale(1); }}
        76% {{ opacity: 0.85; transform: scale(0.96); }}
        80% {{ opacity: 0.35; transform: scale(0.88); }}
        84%, 100% {{ opacity: 0; transform: scale(0.8); }}
      }}
      .packetWsNotify {{ opacity: 0; animation: packetWsNotify {DUR} infinite; }}
      @keyframes packetWsNotify {{
        0%, 32% {{ opacity: 0; transform: translate({wsx}px, {wsy}px); }}
        34% {{ opacity: 1; transform: translate({wsx}px, {wsy}px); }}
        42% {{ opacity: 1; transform: translate({wex}px, {wey}px); }}
        44%, 100% {{ opacity: 0; transform: translate({wex}px, {wey}px); }}
      }}
      .packetGet1 {{ opacity: 0; animation: packetGet1 {DUR} infinite; }}
      @keyframes packetGet1 {{
        0%, 44% {{ opacity: 0; transform: translate(600px, 300px); }}
        46% {{ opacity: 1; transform: translate(600px, 300px); }}
        53% {{ opacity: 1; transform: translate({g1x}px, {g1y}px); }}
        54%, 100% {{ opacity: 0; transform: translate({g1x}px, {g1y}px); }}
      }}
      .packetGet2 {{ opacity: 0; animation: packetGet2 {DUR} infinite; }}
      @keyframes packetGet2 {{
        0%, 50% {{ opacity: 0; transform: translate(600px, 340px); }}
        52% {{ opacity: 1; transform: translate(600px, 340px); }}
        59% {{ opacity: 1; transform: translate({g2x}px, {g2y}px); }}
        60%, 100% {{ opacity: 0; transform: translate({g2x}px, {g2y}px); }}
      }}
      .packetGet3 {{ opacity: 0; animation: packetGet3 {DUR} infinite; }}
      @keyframes packetGet3 {{
        0%, 56% {{ opacity: 0; transform: translate(600px, 380px); }}
        58% {{ opacity: 1; transform: translate(600px, 380px); }}
        65% {{ opacity: 1; transform: translate({g3x}px, {g3y}px); }}
        66%, 100% {{ opacity: 0; transform: translate({g3x}px, {g3y}px); }}
      }}
      #rsAccumTray {{ animation: rsAccumTray {DUR} infinite; }}
      @keyframes rsAccumTray {{
        0%, 53% {{ opacity: 0; }}
        55%, 100% {{ opacity: 1; }}
      }}
      #rsAccumFile1 {{
        transform-origin: center;
        animation: rsAccumFile1 {DUR} infinite;
      }}
      @keyframes rsAccumFile1 {{
        0%, 53% {{ opacity: 0; transform: translate({g1x}px, {g1y}px) scale(0.55); }}
        54% {{ opacity: 1; transform: translate({g1x}px, {g1y}px) scale(0.9); }}
        55% {{ opacity: 1; transform: translate({a1x}px, {a1y}px) scale(1); }}
        56%, 100% {{ opacity: 1; transform: translate({a1x}px, {a1y}px) scale(1); }}
      }}
      #rsAccumFile2 {{
        transform-origin: center;
        animation: rsAccumFile2 {DUR} infinite;
      }}
      @keyframes rsAccumFile2 {{
        0%, 59% {{ opacity: 0; transform: translate({g2x}px, {g2y}px) scale(0.55); }}
        60% {{ opacity: 1; transform: translate({g2x}px, {g2y}px) scale(0.9); }}
        61% {{ opacity: 1; transform: translate({a2x}px, {a2y}px) scale(1); }}
        62%, 100% {{ opacity: 1; transform: translate({a2x}px, {a2y}px) scale(1); }}
      }}
      #rsAccumFile3 {{
        transform-origin: center;
        animation: rsAccumFile3 {DUR} infinite;
      }}
      @keyframes rsAccumFile3 {{
        0%, 65% {{ opacity: 0; transform: translate({g3x}px, {g3y}px) scale(0.55); }}
        66% {{ opacity: 1; transform: translate({g3x}px, {g3y}px) scale(0.9); }}
        67% {{ opacity: 1; transform: translate({a3x}px, {a3y}px) scale(1); }}
        68%, 100% {{ opacity: 1; transform: translate({a3x}px, {a3y}px) scale(1); }}
      }}
      #rsAccumLabel {{ animation: rsAccumLabel {DUR} infinite; }}
      @keyframes rsAccumLabel {{
        0%, 66% {{ opacity: 0; }}
        68%, 100% {{ opacity: 1; }}
      }}
      #fileProgressCount {{ animation: fileProgressCount {DUR} infinite; }}
      @keyframes fileProgressCount {{
        0%, 53% {{ opacity: 0; }}
        55%, 58% {{ opacity: 1; }}
        60%, 100% {{ opacity: 0; }}
      }}
      #fileProgressMid {{ animation: fileProgressMid {DUR} infinite; }}
      @keyframes fileProgressMid {{
        0%, 59% {{ opacity: 0; }}
        61%, 64% {{ opacity: 1; }}
        66%, 100% {{ opacity: 0; }}
      }}
      #fileProgressDone {{ animation: fileProgressDone {DUR} infinite; }}
      @keyframes fileProgressDone {{
        0%, 65% {{ opacity: 0; }}
        67%, 72% {{ opacity: 1; }}
        74%, 100% {{ opacity: 0; }}
      }}
"""


def build_svg(cfg: Dict[str, Any], b64: str) -> str:
    id_sub1, id_sub2 = cfg["id_subtitle"]
    rs_sub1, rs_sub2 = cfg["rs_subtitle"]
    s1a, s1b, s1c = cfg["step1"]
    s4a, s4b = cfg["step4"]
    tray_x = cfg["accum_tray_x"]
    center_x = cfg["accum_center_x"]
    flow_post = cfg["flow_post"]
    flow_ws = cfg["flow_ws"]
    flow_get = cfg["flow_get"]

    parts: List[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 1200 700" width="1200" height="700" role="img" '
        'aria-labelledby="bftTitle bftDesc">\n',
        f'  <title id="bftTitle">{cfg["title"]}</title>\n',
        f'  <desc id="bftDesc">{cfg["desc"]}</desc>\n',
        "  <defs>\n",
        '    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">\n',
        '      <feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#0b1b5f" flood-opacity="0.14"/>\n',
        "    </filter>\n",
        '    <clipPath id="resourceServerClip">\n',
        '      <rect x="848" y="188" width="264" height="168" rx="10"/>\n',
        "    </clipPath>\n",
        "    <style>\n",
        "      .title { font: 700 38px Arial, Helvetica, sans-serif; fill: #06146b; }\n",
        "      .heading { font: 700 24px Arial, Helvetica, sans-serif; fill: #06146b; }\n",
        "      .label { font: 700 20px Arial, Helvetica, sans-serif; fill: #06146b; }\n",
        "      .small { font: 16px Arial, Helvetica, sans-serif; fill: #06146b; }\n",
        "      .panel { fill: #fff; stroke: #cfe0ff; stroke-width: 2; filter: url(#shadow); }\n",
        "      .flowLine { fill: none; stroke: #cbd5e1; stroke-width: 3; stroke-linecap: round; }\n",
        "      .flowLineActive { fill: none; stroke-width: 4; stroke-linecap: round; }\n",
        "      .packetText { font: 700 11px Arial, Helvetica, sans-serif; fill: #fff; }\n",
        "      .packetSub { font: 600 9px Arial, Helvetica, sans-serif; fill: #dbeafe; }\n",
        "      .captionBox { fill: #0f172a; opacity: 0.9; }\n",
        "      .captionText { font: 700 13px Arial, Helvetica, sans-serif; fill: #fff; }\n",
        _anim_style(cfg),
        "    </style>\n",
        "  </defs>\n",
        '  <rect width="1200" height="700" fill="#ffffff"/>\n',
        '  <text x="600" y="58" text-anchor="middle" class="title">Binary file transfer</text>\n',
        '  <g id="imageDisplay">\n',
        '    <rect class="panel" x="95" y="255" width="250" height="190" rx="18"/>\n',
        '    <rect x="185" y="278" width="70" height="58" rx="12" fill="#6528e0"/>\n',
        '    <path d="M200 322 L215 304 L227 317 L236 309 L248 322 Z" fill="#fff"/>\n',
        '    <circle cx="236" cy="296" r="5" fill="#fff"/>\n',
        '    <text x="220" y="364" text-anchor="middle" class="label">Image Display</text>\n',
        f'    <text x="220" y="390" text-anchor="middle" class="small">{id_sub1}</text>\n',
        f'    <text x="220" y="410" text-anchor="middle" class="small">{id_sub2}</text>\n',
        "  </g>\n",
        '  <g id="castHub">\n',
        '    <g id="castHubGraphic">\n',
        '      <circle cx="600" cy="340" r="18" fill="#0b55d9"/>\n',
        '      <circle cx="600" cy="278" r="9" fill="#0b55d9"/>\n',
        '      <circle cx="545" cy="310" r="12" fill="#0b55d9"/>\n',
        '      <circle cx="655" cy="310" r="12" fill="#0b55d9"/>\n',
        '      <circle cx="555" cy="385" r="12" fill="#0b55d9"/>\n',
        '      <circle cx="645" cy="385" r="12" fill="#0b55d9"/>\n',
        '      <line x1="600" y1="340" x2="600" y2="278" stroke="#0b55d9" stroke-width="8"/>\n',
        '      <line x1="600" y1="340" x2="545" y2="310" stroke="#0b55d9" stroke-width="8"/>\n',
        '      <line x1="600" y1="340" x2="655" y2="310" stroke="#0b55d9" stroke-width="8"/>\n',
        '      <line x1="600" y1="340" x2="555" y2="385" stroke="#0b55d9" stroke-width="8"/>\n',
        '      <line x1="600" y1="340" x2="645" y2="385" stroke="#0b55d9" stroke-width="8"/>\n',
        "    </g>\n",
        '    <text x="600" y="430" text-anchor="middle" class="heading">Cast Hub</text>\n',
        '    <text x="600" y="456" text-anchor="middle" class="small">HTTP payload store</text>\n',
        '    <g id="hubPayloadStack">\n',
        '      <rect x="562" y="248" width="28" height="36" rx="4" fill="#dbeafe" stroke="#2457d6" stroke-width="2"/>\n',
        '      <rect x="586" y="242" width="28" height="36" rx="4" fill="#dbeafe" stroke="#2457d6" stroke-width="2"/>\n',
        '      <rect x="610" y="236" width="28" height="36" rx="4" fill="#dbeafe" stroke="#2457d6" stroke-width="2"/>\n',
        '      <text x="600" y="228" text-anchor="middle" font-family="Arial" font-size="10" font-weight="700" fill="#2457d6">payloadId ×3</text>\n',
        '      <text x="600" y="292" text-anchor="middle" font-family="Arial" font-size="9" font-weight="700" fill="#94a3b8">in-memory store</text>\n',
        "    </g>\n",
        "  </g>\n",
        '  <g id="resourceServer">\n',
        '    <rect class="panel" x="835" y="165" width="290" height="350" rx="18"/>\n',
        f'    <image xlink:href="data:image/png;base64,{b64}" href="data:image/png;base64,{b64}" '
        'x="848" y="188" width="264" height="168" preserveAspectRatio="xMidYMid meet" '
        'clip-path="url(#resourceServerClip)"/>\n',
        '    <text x="980" y="380" text-anchor="middle" class="label">Resource Server</text>\n',
        f'    <text x="980" y="406" text-anchor="middle" class="small">{rs_sub1}</text>\n',
        f'    <text x="980" y="426" text-anchor="middle" class="small">{rs_sub2}</text>\n',
        "  </g>\n",
        f'  <path class="flowLine" d="{flow_post}"/>\n',
        f'  <path id="flowLinePost" class="flowLineActive" d="{flow_post}" stroke="#2457d6"/>\n',
        f'  <path class="flowLine" d="{flow_ws}"/>\n',
        f'  <path id="flowLineWs" class="flowLineActive" d="{flow_ws}" stroke="#2457d6"/>\n',
        f'  <path id="flowLineGet" class="flowLineActive" d="{flow_get}" stroke="#1f9d55"/>\n',
        '  <g id="step1Caption">\n',
        '    <rect class="captionBox" x="120" y="82" width="960" height="58" rx="8"/>\n',
        f'    <text x="600" y="102" text-anchor="middle" class="captionText">{s1a}</text>\n',
        f'    <text x="600" y="118" text-anchor="middle" class="captionText" font-size="11">{s1b}</text>\n',
        f'    <text x="600" y="134" text-anchor="middle" class="captionText" font-size="11">{s1c}</text>\n',
        "  </g>\n",
        '  <g id="step2Caption">\n',
        '    <rect class="captionBox" x="380" y="88" width="440" height="44" rx="8"/>\n',
        '    <text x="600" y="108" text-anchor="middle" class="captionText">Step 2: Hub stores bytes; adds payloadId per files[] entry</text>\n',
        '    <text x="600" y="126" text-anchor="middle" class="captionText" font-size="11">WebSocket will carry metadata only</text>\n',
        "  </g>\n",
        '  <g id="step3Caption">\n',
        '    <rect class="captionBox" x="330" y="88" width="540" height="44" rx="8"/>\n',
        '    <text x="600" y="108" text-anchor="middle" class="captionText">Step 3: Hub fans out dicom-send JSON (files[].payloadId)</text>\n',
        f'    <text x="600" y="126" text-anchor="middle" class="captionText" font-size="11">{cfg["step3_ws"]}</text>\n',
        "  </g>\n",
        '  <g id="step4Caption">\n',
        '    <rect class="captionBox" x="240" y="88" width="720" height="44" rx="8"/>\n',
        f'    <text x="600" y="108" text-anchor="middle" class="captionText">{s4a}</text>\n',
        f'    <text x="600" y="126" text-anchor="middle" class="captionText" font-size="11">{s4b}</text>\n',
        "  </g>\n",
        '  <g id="step5Caption">\n',
        '    <rect class="captionBox" x="300" y="88" width="600" height="44" rx="8"/>\n',
        '    <text x="600" y="108" text-anchor="middle" class="captionText">Step 5: Payload expires — files removed from hub memory</text>\n',
        '    <text x="600" y="126" text-anchor="middle" class="captionText" font-size="11">CAST_HUB_HTTP_PAYLOAD_TTL_SECONDS (default 300 s)</text>\n',
        "  </g>\n",
        f'  <g id="uploadFileStack">{FILE_STACK_INNER}\n',
        '    <text x="38" y="-6" text-anchor="middle" font-family="Arial" font-size="10" font-weight="700" fill="#2457d6">3 files</text>\n',
        "  </g>\n",
        '  <g class="packetStowPost">\n',
        '    <rect x="-92" y="-20" width="184" height="40" rx="18" fill="#2457d6"/>\n',
        '    <text x="0" y="-4" text-anchor="middle" class="packetSub">HTTP POST</text>\n',
        '    <text x="0" y="11" text-anchor="middle" class="packetText">multipart + files</text>\n',
        "  </g>\n",
        '  <g class="packetWsNotify">\n',
        '    <rect x="-78" y="-16" width="156" height="32" rx="16" fill="#2457d6"/>\n',
        '    <text x="0" y="-2" text-anchor="middle" class="packetSub">WebSocket</text>\n',
        '    <text x="0" y="12" text-anchor="middle" class="packetText">dicom-send JSON</text>\n',
        "  </g>\n",
        '  <g class="packetGet1">\n',
        '    <rect x="-82" y="-16" width="164" height="32" rx="16" fill="#1f9d55"/>\n',
        '    <rect x="-68" y="-8" width="14" height="18" rx="2" fill="#dbeafe" stroke="#fff" stroke-width="1"/>\n',
        '    <text x="-48" y="-2" text-anchor="start" class="packetSub">GET req</text>\n',
        '    <text x="-48" y="12" text-anchor="start" class="packetText">+ file</text>\n',
        "  </g>\n",
        '  <g class="packetGet2">\n',
        '    <rect x="-82" y="-16" width="164" height="32" rx="16" fill="#1f9d55"/>\n',
        '    <rect x="-68" y="-8" width="14" height="18" rx="2" fill="#dbeafe" stroke="#fff" stroke-width="1"/>\n',
        '    <text x="-48" y="-2" text-anchor="start" class="packetSub">GET req</text>\n',
        '    <text x="-48" y="12" text-anchor="start" class="packetText">+ file</text>\n',
        "  </g>\n",
        '  <g class="packetGet3">\n',
        '    <rect x="-82" y="-16" width="164" height="32" rx="16" fill="#1f9d55"/>\n',
        '    <rect x="-68" y="-8" width="14" height="18" rx="2" fill="#dbeafe" stroke="#fff" stroke-width="1"/>\n',
        '    <text x="-48" y="-2" text-anchor="start" class="packetSub">GET req</text>\n',
        '    <text x="-48" y="12" text-anchor="start" class="packetText">+ file</text>\n',
        "  </g>\n",
        '  <g id="rsAccumulatedFiles">\n',
        f'    <rect id="rsAccumTray" x="{tray_x}" y="524" width="244" height="58" rx="10" fill="#f0fdf4" stroke="#86efac" stroke-width="2"/>\n',
        '    <g id="rsAccumFile1">\n',
        '      <rect x="-14" y="-18" width="28" height="36" rx="4" fill="#bbf7d0" stroke="#16a34a" stroke-width="2"/>\n',
        "    </g>\n",
        '    <g id="rsAccumFile2">\n',
        '      <rect x="-14" y="-18" width="28" height="36" rx="4" fill="#bbf7d0" stroke="#16a34a" stroke-width="2"/>\n',
        "    </g>\n",
        '    <g id="rsAccumFile3">\n',
        '      <rect x="-14" y="-18" width="28" height="36" rx="4" fill="#bbf7d0" stroke="#16a34a" stroke-width="2"/>\n',
        "    </g>\n",
        f'    <text id="fileProgressCount" x="{center_x}" y="548" text-anchor="middle" font-family="Arial" font-size="11" font-weight="700" fill="#166534">1 / 3 fetched</text>\n',
        f'    <text id="fileProgressMid" x="{center_x}" y="548" text-anchor="middle" font-family="Arial" font-size="11" font-weight="700" fill="#166534">2 / 3 fetched</text>\n',
        f'    <text id="fileProgressDone" x="{center_x}" y="548" text-anchor="middle" font-family="Arial" font-size="11" font-weight="700" fill="#166534">3 / 3 fetched</text>\n',
        f'    <text id="rsAccumLabel" x="{center_x}" y="572" text-anchor="middle" font-family="Arial" font-size="11" font-weight="700" fill="#166534">files accumulate here (files[].data)</text>\n',
        "  </g>\n",
        "</svg>\n",
    ]
    return "".join(parts)


def _load_embedded_png_b64() -> str:
    for path in (SRC, SRC_FALLBACK):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        b64m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", text)
        if b64m:
            return b64m.group(1)
    raise SystemExit(
        f"embedded PNG not found in {SRC.name} or {SRC_FALLBACK.name}"
    )


def main() -> None:
    b64 = _load_embedded_png_b64()

    for name, cfg in DIRECTIONS.items():
        out = cfg["out"]
        svg = build_svg(cfg, b64)
        out.write_text(svg, encoding="utf-8", newline="\n")
        print("wrote", out.name, len(svg), f"({name})")


if __name__ == "__main__":
    main()
