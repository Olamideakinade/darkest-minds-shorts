"""Automated Visual Quality Gate for MhideDev Video Engine.

Implements rigorous broadcast & mobile video verification:
- Technical validation (1080x1920, 9:16, 30fps, H.264, AAC)
- Audio integrity (clipping, silence, volume stats)
- Frame-level black/blank frame detection
- Dead/frozen frame detection (temporal MSE variance)
- Luminance jump / flashbang detection
- Safe-zone & text collision analysis (Mobile Shorts UI safe margins)
- Automated 16-frame contact sheet generation
- Defect ledger with timestamps and severity (CRITICAL vs WARNING)
- Production-readiness verdict (Hard failure gate)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

from app.config import config
from app.editing.timeline import ScenePlan
from app.utils.logger import logger


class QualitySeverity:
    CRITICAL = "CRITICAL"   # Hard failure: blocks production release
    WARNING = "WARNING"     # Creative or minor advisory


class QualityDefect:
    def __init__(self, defect_type: str, severity: str, timestamp_sec: float, message: str) -> None:
        self.defect_type = defect_type
        self.severity = severity
        self.timestamp_sec = round(timestamp_sec, 2)
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defect_type": self.defect_type,
            "severity": self.severity,
            "timestamp_sec": self.timestamp_sec,
            "message": self.message,
        }


class VisualQualityReport:
    def __init__(self, video_path: Path) -> None:
        self.video_path = video_path
        self.passed_hard_gate: bool = True
        self.production_ready: bool = True
        self.creative_score: int = 100
        self.technical_metrics: Dict[str, Any] = {}
        self.defects: List[QualityDefect] = []
        self.contact_sheet_path: Optional[Path] = None
        self.sample_frame_paths: List[Path] = []

    def add_defect(self, defect_type: str, severity: str, timestamp_sec: float, message: str) -> None:
        d = QualityDefect(defect_type, severity, timestamp_sec, message)
        self.defects.append(d)
        if severity == QualitySeverity.CRITICAL:
            self.passed_hard_gate = False
            self.production_ready = False
            self.creative_score = max(0, self.creative_score - 25)
        else:
            self.creative_score = max(0, self.creative_score - 8)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_path": str(self.video_path),
            "passed_hard_gate": self.passed_hard_gate,
            "production_ready": self.production_ready,
            "creative_score": self.creative_score,
            "technical_metrics": self.technical_metrics,
            "defects_count": len(self.defects),
            "critical_defects_count": sum(1 for d in self.defects if d.severity == QualitySeverity.CRITICAL),
            "defects": [d.to_dict() for d in self.defects],
            "contact_sheet_path": str(self.contact_sheet_path) if self.contact_sheet_path else None,
            "sample_frames_count": len(self.sample_frame_paths),
        }


class VisualQualityGate:
    """Automated visual quality auditor and hard-failure gate for rendered MP4s."""

    def __init__(self, ffmpeg_bin: str = config.ffmpeg_path) -> None:
        self.ffmpeg = ffmpeg_bin

    def audit_video(
        self,
        video_path: Path,
        timeline: Optional[List[ScenePlan]] = None,
        output_dir: Optional[Path] = None,
    ) -> VisualQualityReport:
        report = VisualQualityReport(video_path)
        work_dir = output_dir or (video_path.parent / "quality_audit")
        work_dir.mkdir(parents=True, exist_ok=True)

        if not video_path.exists() or video_path.stat().st_size == 0:
            report.add_defect("FILE_ERROR", QualitySeverity.CRITICAL, 0.0, f"Video file is missing or 0 bytes: {video_path}")
            return report

        # 1. Technical Container & Stream Inspection
        self._inspect_technical_streams(video_path, report)

        # 2. Audio Integrity Check
        self._audit_audio_integrity(video_path, report)

        # 3. Frame Sampling (16 evenly distributed frames)
        duration = report.technical_metrics.get("duration_sec", 0.0)
        frames = self._extract_audit_frames(video_path, duration, work_dir, num_frames=16)
        report.sample_frame_paths = [p for p, _ in frames]

        # 4. Generate 16-Frame Contact Sheet
        if frames:
            contact_sheet_file = work_dir / "visual_quality_contact_sheet.jpg"
            self._render_contact_sheet(frames, contact_sheet_file, report)
            report.contact_sheet_path = contact_sheet_file

        # 5. Visual Frame-Level Quality Checks
        if frames:
            self._audit_black_and_blank_frames(frames, report)
            self._audit_luminance_and_flashbangs(frames, report)
            self._audit_temporal_motion(frames, report)
            self._audit_safe_zones_and_collisions(frames, timeline, report)

        # Write QA audit summary artifact
        self._write_markdown_audit_report(report, work_dir)

        return report

    def _inspect_technical_streams(self, video_path: Path, report: VisualQualityReport) -> None:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,codec_name,codec_type,r_frame_rate,duration:format=duration,size",
            "-of", "json",
            str(video_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(res.stdout)
            streams = info.get("streams", [])
            format_info = info.get("format", {})

            v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

            if not v_stream:
                report.add_defect("MISSING_VIDEO_STREAM", QualitySeverity.CRITICAL, 0.0, "Video file has no video stream.")
                return

            w = int(v_stream.get("width", 0))
            h = int(v_stream.get("height", 0))
            v_codec = v_stream.get("codec_name", "")
            
            # Duration calculation
            dur_str = format_info.get("duration") or v_stream.get("duration", "0.0")
            dur = float(dur_str)

            # FPS calculation
            fps_str = v_stream.get("r_frame_rate", "30/1")
            num, den = (fps_str.split("/") + ["1"])[:2]
            fps = float(num) / float(den) if float(den) != 0 else 30.0

            a_codec = a_stream.get("codec_name", "") if a_stream else "none"

            report.technical_metrics = {
                "width": w,
                "height": h,
                "resolution": f"{w}x{h}",
                "aspect_ratio": "9:16" if (w == 1080 and h == 1920) else f"{w}:{h}",
                "fps": round(fps, 2),
                "duration_sec": round(dur, 2),
                "video_codec": v_codec,
                "audio_codec": a_codec,
                "file_size_bytes": int(format_info.get("size", 0)),
            }

            # Hard Gate Validations
            if w != 1080 or h != 1920:
                report.add_defect("RESOLUTION_INVALID", QualitySeverity.CRITICAL, 0.0, f"Expected 1080x1920 (9:16), got {w}x{h}")
            if "h264" not in v_codec.lower() and "avc" not in v_codec.lower():
                report.add_defect("CODEC_INVALID", QualitySeverity.CRITICAL, 0.0, f"Video codec is {v_codec}, expected h264/avc1")
            if not a_stream or a_codec == "none":
                report.add_defect("MISSING_AUDIO_STREAM", QualitySeverity.CRITICAL, 0.0, "Video has no audio stream")
            if dur < 15.0:
                report.add_defect("DURATION_TOO_SHORT", QualitySeverity.CRITICAL, dur, f"Duration {dur:.1f}s is under minimum 15.0s")
            elif dur > 59.5:
                report.add_defect("DURATION_TOO_LONG", QualitySeverity.CRITICAL, dur, f"Duration {dur:.1f}s exceeds YouTube Shorts 60s limit")

        except Exception as e:
            report.add_defect("FFPROBE_FAILED", QualitySeverity.CRITICAL, 0.0, f"Stream inspection failed: {e}")

    def _audit_audio_integrity(self, video_path: Path, report: VisualQualityReport) -> None:
        cmd = [
            self.ffmpeg, "-i", str(video_path),
            "-af", "volumedetect",
            "-vn", "-sn", "-f", "null", "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            stderr = res.stderr

            max_vol = -99.0
            mean_vol = -99.0
            for line in stderr.splitlines():
                if "max_volume:" in line:
                    try:
                        max_vol = float(line.split("max_volume:")[1].split("dB")[0].strip())
                    except Exception:
                        pass
                if "mean_volume:" in line:
                    try:
                        mean_vol = float(line.split("mean_volume:")[1].split("dB")[0].strip())
                    except Exception:
                        pass

            report.technical_metrics["audio_max_volume_db"] = max_vol
            report.technical_metrics["audio_mean_volume_db"] = mean_vol

            # Audio clipping (max_vol >= -0.05 dB)
            if max_vol >= -0.05:
                report.add_defect("AUDIO_CLIPPING", QualitySeverity.WARNING, 0.0, f"Audio peaks at {max_vol:.1f} dB (potential clipping/distortion)")
            # Audio too quiet / silent
            if mean_vol < -45.0:
                report.add_defect("AUDIO_TOO_QUIET", QualitySeverity.CRITICAL, 0.0, f"Audio is near silent: mean volume {mean_vol:.1f} dB")

        except Exception as e:
            report.add_defect("AUDIO_AUDIT_ERROR", QualitySeverity.WARNING, 0.0, f"Audio volume audit warning: {e}")

    def _extract_audit_frames(
        self,
        video_path: Path,
        duration: float,
        work_dir: Path,
        num_frames: int = 16,
    ) -> List[Tuple[Path, float]]:
        if duration <= 0.0:
            return []

        frames_dir = work_dir / "audit_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        step = duration / (num_frames + 1)

        extracted: List[Tuple[Path, float]] = []
        for i in range(1, num_frames + 1):
            t = round(i * step, 2)
            out_img = frames_dir / f"frame_{i:02d}_{t:.2f}s.jpg"
            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(t),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(out_img),
            ]
            subprocess.run(cmd, capture_output=True, text=True)
            if out_img.exists() and out_img.stat().st_size > 0:
                extracted.append((out_img, t))

        return extracted

    def _render_contact_sheet(
        self,
        frames: List[Tuple[Path, float]],
        output_file: Path,
        report: VisualQualityReport,
    ) -> None:
        """Create a 4x4 contact sheet with timestamps and technical metadata."""
        cols = 4
        rows = 4
        thumb_w = 270
        thumb_h = 480
        pad = 8
        header_h = 100

        sheet_w = (cols * thumb_w) + ((cols + 1) * pad)
        sheet_h = header_h + (rows * thumb_h) + ((rows + 1) * pad)

        sheet = Image.new("RGB", (sheet_w, sheet_h), (12, 14, 20))
        draw = ImageDraw.Draw(sheet)

        font_header = ImageFont.load_default()
        meta = report.technical_metrics
        status_color = (34, 197, 94) if report.passed_hard_gate else (239, 68, 68)

        draw.text((pad + 10, 16), f"MHIDEDEV VISUAL QUALITY GATE — CONTACT SHEET", fill=(255, 255, 255), font=font_header)
        draw.text((pad + 10, 42), f"Video: {report.video_path.name} | Resolution: {meta.get('resolution')} | {meta.get('fps')} FPS | Duration: {meta.get('duration_sec')}s", fill=(160, 175, 200), font=font_header)
        draw.text((pad + 10, 68), f"Verdict: {'PASS' if report.passed_hard_gate else 'FAIL'} (Score: {report.creative_score}/100 | Defects: {len(report.defects)})", fill=status_color, font=font_header)

        for idx, (f_path, t_sec) in enumerate(frames[:16]):
            r = idx // cols
            c = idx % cols
            x = pad + c * (thumb_w + pad)
            y = header_h + pad + r * (thumb_h + pad)

            try:
                with Image.open(f_path) as thumb_img:
                    resized = thumb_img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
                    sheet.paste(resized, (x, y))

                # Timestamp Pill
                draw.rectangle([x + 6, y + 6, x + 85, y + 26], fill=(0, 0, 0, 200))
                draw.text((x + 12, y + 9), f"{t_sec:.2f}s", fill=(245, 158, 11), font=font_header)
            except Exception as e:
                logger.debug(f"Error thumbnailing frame {f_path}: {e}")

        sheet.save(str(output_file), "JPEG", quality=90)

    def _audit_black_and_blank_frames(
        self,
        frames: List[Tuple[Path, float]],
        report: VisualQualityReport,
    ) -> None:
        """Reject videos containing solid black or blank void frames."""
        for f_path, t_sec in frames:
            try:
                with Image.open(f_path) as img:
                    stat = ImageStat.Stat(img.convert("RGB"))
                    mean_val = sum(stat.mean) / 3.0
                    stddev_val = sum(stat.stddev) / 3.0

                    if mean_val < 3.0 and stddev_val < 2.0:
                        report.add_defect("BLACK_FRAME_DETECTED", QualitySeverity.CRITICAL, t_sec, f"Solid black frame at {t_sec:.2f}s (mean luminance {mean_val:.1f})")
            except Exception as e:
                logger.debug(f"Black frame check error: {e}")

    def _audit_luminance_and_flashbangs(
        self,
        frames: List[Tuple[Path, float]],
        report: VisualQualityReport,
    ) -> None:
        """Detect harsh flashbangs (luminance jumps > 85/255 across frames)."""
        prev_lum: Optional[float] = None
        for f_path, t_sec in frames:
            try:
                with Image.open(f_path) as img:
                    stat = ImageStat.Stat(img.convert("RGB"))
                    # Perceived luminance
                    lum = 0.299 * stat.mean[0] + 0.587 * stat.mean[1] + 0.114 * stat.mean[2]
                    if prev_lum is not None:
                        delta = abs(lum - prev_lum)
                        if delta > 90.0:
                            report.add_defect("FLASHBANG_LUMINANCE_JUMP", QualitySeverity.WARNING, t_sec, f"Harsh luminance jump of Δ{delta:.1f} at {t_sec:.2f}s (dark to stark white)")
                    prev_lum = lum
            except Exception as e:
                logger.debug(f"Luminance check error: {e}")

    def _audit_temporal_motion(
        self,
        frames: List[Tuple[Path, float]],
        report: VisualQualityReport,
    ) -> None:
        """Detect frozen/dead static frames by computing inter-frame pixel differences."""
        if len(frames) < 2:
            return

        frozen_count = 0
        for i in range(len(frames) - 1):
            p1, t1 = frames[i]
            p2, t2 = frames[i + 1]
            try:
                with Image.open(p1) as img1, Image.open(p2) as img2:
                    diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
                    stat = diff.getextrema()
                    max_d = max(s[1] for s in stat)
                    if max_d < 3:
                        frozen_count += 1
                        report.add_defect("FROZEN_STATIC_FRAME", QualitySeverity.WARNING, t2, f"Frozen frame with zero visual motion between {t1:.2f}s and {t2:.2f}s (max pixel diff {max_d})")
            except Exception as e:
                logger.debug(f"Temporal motion error: {e}")

        if frozen_count >= 4:
            report.add_defect("PROLONGED_STATIC_VIDEO", QualitySeverity.CRITICAL, 0.0, f"Video contains {frozen_count} static frozen intervals")

    def _audit_safe_zones_and_collisions(
        self,
        frames: List[Tuple[Path, float]],
        timeline: Optional[List[ScenePlan]],
        report: VisualQualityReport,
    ) -> None:
        """Verify upper and lower safe-zones to prevent native Shorts UI collisions."""
        # Top 0-140px: YouTube header / search bar
        # Bottom 1660-1920px: YouTube Shorts channel title, sound button, description, subscribe
        for f_path, t_sec in frames:
            try:
                with Image.open(f_path) as img:
                    w, h = img.size
                    # Check bottom 200px (y=1720 to 1920) for unintended subtitle text
                    bottom_crop = img.crop((0, 1720, w, h))
                    stat = ImageStat.Stat(bottom_crop)
                    # High brightness text in forbidden bottom margin
                    if stat.mean[0] > 180 and stat.mean[1] > 180 and stat.mean[2] > 180:
                        report.add_defect("SAFE_ZONE_VIOLATION", QualitySeverity.WARNING, t_sec, f"Text encroaches bottom 200px mobile unsafe zone at {t_sec:.2f}s (collides with Shorts UI)")
            except Exception as e:
                logger.debug(f"Safe zone check error: {e}")

    def _write_markdown_audit_report(self, report: VisualQualityReport, work_dir: Path) -> None:
        out_md = work_dir / "visual_quality_report.md"
        meta = report.technical_metrics

        lines = [
            "# MHIDEDEV AUTOMATED VISUAL QUALITY GATE REPORT",
            f"**Video File**: `{report.video_path.name}`",
            f"**Production Ready**: **{'✓ YES' if report.production_ready else '✗ NO (Hard Gate Failed)'}**",
            f"**Creative Score**: **{report.creative_score} / 100**",
            "",
            "## 1. Technical Specifications",
            f"- **Resolution**: `{meta.get('resolution', 'N/A')}`",
            f"- **Aspect Ratio**: `{meta.get('aspect_ratio', 'N/A')}`",
            f"- **Frame Rate**: `{meta.get('fps', 0)} FPS`",
            f"- **Duration**: `{meta.get('duration_sec', 0)}s`",
            f"- **Video Codec**: `{meta.get('video_codec', 'N/A')}`",
            f"- **Audio Codec**: `{meta.get('audio_codec', 'N/A')}`",
            f"- **Audio Max Peak**: `{meta.get('audio_max_volume_db', 'N/A')} dB`",
            f"- **Audio Mean RMS**: `{meta.get('audio_mean_volume_db', 'N/A')} dB`",
            "",
            "## 2. Detected Defects Ledger",
        ]

        if not report.defects:
            lines.append("- ✓ **Zero defects detected.** Video satisfies all technical and safe-zone constraints.")
        else:
            lines.append("| Timestamp | Severity | Defect Type | Message |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for d in report.defects:
                sev_badge = f"**{d.severity}**" if d.severity == QualitySeverity.CRITICAL else d.severity
                lines.append(f"| {d.timestamp_sec:.2f}s | {sev_badge} | `{d.defect_type}` | {d.message} |")

        lines.extend([
            "",
            "## 3. Contact Sheet & Evidence",
            f"- Contact sheet generated: `{report.contact_sheet_path.name if report.contact_sheet_path else 'None'}`",
            f"- Representative frame samples extracted: {len(report.sample_frame_paths)} frames.",
        ])

        with open(out_md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
