"""Style learning and style application engine for MhideDev content.

Translates analyzed reference editing patterns and comedic/educational techniques
into original, brand-authentic creative specifications without copying content.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.editing.style_library import EditingStyleLibrary, editing_style_library
from app.research.reference_analyzer import ReferenceAnalysisResult


@dataclass
class StyleAdaptationSpec:
    """Creative specification adapting an observed technique to the MhideDev brand."""

    source_technique_id: str
    reusable_principle: str
    mhide_dev_adaptation: str
    target_content_pillar: str
    scene_visual_type: str  # code_editor, terminal_crash, split_comparison, confession_card, browser_preview
    visual_parameters: Dict[str, Any] = field(default_factory=dict)
    audio_parameters: Dict[str, Any] = field(default_factory=dict)
    anti_copying_rules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StyleAdapter:
    """Adapts analyzed video techniques into original MhideDev developer creative specs."""

    def __init__(self, library: Optional[EditingStyleLibrary] = None) -> None:
        self.library = library or editing_style_library

    def adapt_reference(
        self,
        analysis: ReferenceAnalysisResult,
        target_pillar: str = "shared_developer_confessions",
    ) -> List[StyleAdaptationSpec]:
        """Convert reference analysis observations into original MhideDev creative specs."""
        specs: List[StyleAdaptationSpec] = []

        # 1. Pacing & Cut Frequency Adaptation
        if analysis.facts.avg_shot_duration_sec < 3.0:
            specs.append(
                StyleAdaptationSpec(
                    source_technique_id="fast_screen_cut",
                    reusable_principle="Rapid cut tempo (every 1.8s–2.5s) prevents visual fatigue and maintains high cognitive velocity.",
                    mhide_dev_adaptation="Alternate every 2 seconds between realistic VS Code syntax editor and interactive ZSH terminal output.",
                    target_content_pillar=target_pillar,
                    scene_visual_type="code_editor",
                    visual_parameters={"cut_interval_sec": 2.2, "editor_theme": "one_dark_pro"},
                    audio_parameters={"cut_foley": "mechanical_keypress"},
                    anti_copying_rules=[
                        "Do not replicate reference creator's custom code snippets or exact fonts.",
                        "Use original Python/TypeScript/SQL code bugs representative of real engineering hurdles.",
                    ],
                )
            )

        # 2. Hook Adaptation based on observed hook type
        hook_type = analysis.creative.hook_category
        if hook_type == "unexpected_failure":
            specs.append(
                StyleAdaptationSpec(
                    source_technique_id="cold_open_crisis",
                    reusable_principle="Open immediately with an active high-stakes production catastrophe within 1.2 seconds.",
                    mhide_dev_adaptation="Open with a live terminal output displaying 'HTTP 500: Database Connection Pool Exhausted' at 5:02 PM on a Friday.",
                    target_content_pillar="shared_developer_confessions",
                    scene_visual_type="terminal_crash",
                    visual_parameters={"error_code": "FATAL_500", "flash_red": True, "punch_in_zoom": 1.25},
                    audio_parameters={"sfx": "subtle_alarm_pulse", "duck_bgm_db": -22.0},
                    anti_copying_rules=[
                        "Write completely original developer scripts.",
                        "Never mention or mimic the competitor's personal handle or catchphrases.",
                    ],
                )
            )
        elif hook_type == "relatable_pain":
            specs.append(
                StyleAdaptationSpec(
                    source_technique_id="split_screen_comparison",
                    reusable_principle="Direct visual contrast between expectation and painful engineering reality.",
                    mhide_dev_adaptation="Split-screen: Top card shows 'Localhost: works perfectly with 1 test user', Bottom card shows 'Cloud Deploy: 10,000 requests timeouts'.",
                    target_content_pillar="programming_humour",
                    scene_visual_type="split_comparison",
                    visual_parameters={"top_status": "200_OK", "bottom_status": "504_TIMEOUT"},
                    audio_parameters={"contrast_sfx": ["peaceful_chime", "record_scratch"]},
                    anti_copying_rules=[
                        "Design original layout graphics in MhideDev brand palette (charcoal, neon amber, cyan).",
                    ],
                )
            )

        # 3. Micro-silence punchline adaptation
        if "silence_before_punchline" in analysis.creative.detected_techniques:
            specs.append(
                StyleAdaptationSpec(
                    source_technique_id="silence_before_punchline",
                    reusable_principle="A 300ms beat of dead silence right before the punchline magnifies comedic impact.",
                    mhide_dev_adaptation="Cut music and voiceover to silence for 300ms immediately before showing the Git blame confirming you wrote the bug 2 years ago.",
                    target_content_pillar=target_pillar,
                    scene_visual_type="code_editor",
                    visual_parameters={"highlight_git_blame": True},
                    audio_parameters={"pre_punchline_silence_ms": 300, "punchline_sfx": "dry_cough_or_gong"},
                    anti_copying_rules=[
                        "Keep audio design fully original using licensed CC0 or synthesized audio stems.",
                    ],
                )
            )

        return specs


# Singleton instance
style_adapter = StyleAdapter()
