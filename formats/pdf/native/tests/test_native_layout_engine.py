from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rebuild = load_module("native_selectable_rebuild", "native_selectable_rebuild.py")
pipeline = load_module("pdf_translation_pipeline_layout", "pdf_translation_pipeline.py")


class NativeTextStreamTests(unittest.TestCase):
    def test_strip_native_text_handles_ascii85_flate_content_streams(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "ascii85-source.pdf"
            pdf = canvas.Canvas(str(source))
            pdf.drawString(72, 720, "Source text")
            pdf.save()

            source_reader = PdfReader(str(source))
            self.assertEqual(
                source_reader.pages[0]["/Contents"].get_object()["/Filter"],
                ["/ASCII85Decode", "/FlateDecode"],
            )

            writer, removed = rebuild.strip_native_text(source)
            output = Path(temp_dir) / "stripped.pdf"
            with output.open("wb") as stream:
                writer.write(stream)

            self.assertGreater(removed, 0)
            self.assertNotIn("Source text", PdfReader(str(output)).pages[0].extract_text())


def require(module, name: str):
    function = getattr(module, name, None)
    if function is None:
        raise AssertionError(f"Required layout function is missing: {name}")
    return function


def block(
    block_id: str,
    text: str,
    translation: str,
    box: list[float],
    *,
    font: str = "ABCDEE+FangSong",
    size: float = 16.0,
    align: int = 0,
):
    return {
        "id": block_id,
        "source_text": text,
        "translation": translation,
        "bbox": box,
        "role": f"body-{size:g}",
        "style": {
            "font": font,
            "size": size,
            "role_size": size,
            "bold": False,
            "italic": False,
            "align": align,
            "rotation": 0,
            "color_rgb": [0, 0, 0],
        },
        "runs": [{"font": font, "size": size, "bold": False}],
        "lines": [{"text": text, "bbox": box, "characters": [], "runs": []}],
    }


class SourceTypographyTests(unittest.TestCase):
    def test_cjk_text_uses_a_font_with_chinese_glyphs(self):
        font_path = pipeline.font_file({"bold": False, "italic": False, "cjk": True})
        self.assertTrue(font_path.lower().endswith(("simsun.ttc", "simsun.ttf")))

    def test_cjk_text_wraps_by_characters_without_inserting_spaces(self):
        draw = ImageDraw.Draw(Image.new("RGB", (800, 160), "white"))
        text = "这是一个用于测试中文换行的长句子。"
        slots = [[0, 0, 90, 16], [0, 18, 90, 34], [0, 36, 90, 52]]
        _, lines, _ = rebuild.fit_text_to_slots(
            draw,
            text,
            r"C:\Windows\Fonts\simsun.ttc",
            10 * rebuild.LAYOUT_SCALE,
            slots,
            minimum_scale=0.5,
        )
        self.assertGreater(len(lines), 1)
        self.assertEqual(text, "".join(lines))


class PageLayoutWrapperTests(unittest.TestCase):
    def test_full_width_header_body_and_footer_rows_are_unwrapped_together(self):
        page = {
            "page": 1,
            "width": 612.0,
            "height": 792.0,
            "table_cells": [
                {"bbox": [0.0, -7.92, 612.0, 89.27]},
                {"bbox": [0.0, 89.27, 612.0, 774.81]},
                {"bbox": [0.0, 774.81, 612.0, 784.08]},
                {"bbox": [0.0, 784.08, 612.0, 800.18]},
            ],
            "blocks": [
                block("p0001-b0001", "Header", "页眉", [111.0, 36.8, 551.0, 53.1], size=16),
                block("p0001-b0002", "Body", "正文", [61.7, 113.2, 551.0, 123.2], size=10),
                block("p0001-b0003", "Footer", "页脚", [75.0, 786.0, 530.0, 796.0], size=9),
            ],
        }

        rebuild.unwrap_page_layout_table(page)

        self.assertEqual([], page["table_cells"])
        self.assertEqual("running-header", page["blocks"][0]["role"])
        self.assertTrue(page["blocks"][1]["role"].startswith("body-"))
        self.assertEqual("footer", page["blocks"][2]["role"])

    def test_pipeline_box_text_wraps_cjk_without_spaces(self):
        draw = ImageDraw.Draw(Image.new("RGB", (800, 160), "white"))
        text = "这是一个用于测试中文换行的长句子。"
        font = ImageFont.truetype(r"C:\Windows\Fonts\simsun.ttc", 40)
        lines = pipeline.wrap_paragraph(draw, text, font, 360)
        self.assertGreater(len(lines), 1)
        self.assertEqual(text, "".join(lines))

    def test_tiny_protected_page_number_keeps_a_glyph_sized_container(self):
        item = block("p0001-b0007", "1", "1", [548.28, 749.44, 552.78, 758.44], size=9)
        item["characters"] = [{"text": "1", "protected": True}]
        item["lines"] = []
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "content_bounds": [42.0, 550.28],
            "table_cells": [],
            "image_boxes": [],
        }
        container = rebuild.resolve_text_container(page, item, {"bbox": item["bbox"]})
        self.assertGreaterEqual(container[2] - container[0], 6.0)

    def test_single_column_body_can_use_empty_right_side_of_page(self):
        item = block(
            "p0001-b0019",
            "窑顶加料装置整体用保温板包装。",
            "The kiln-top charging device is enclosed with insulation panels.",
            [63.6, 630.7, 368.0, 641.1],
            size=10.5,
        )
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "content_bounds": [42.6, 368.0],
            "table_cells": [],
            "image_boxes": [[244.2, 659.4, 372.0, 744.5]],
            "blocks": [item],
        }
        container = rebuild.resolve_text_container(page, item, item["lines"][0])
        self.assertGreater(container[2], 500)

    def test_heading_can_use_empty_right_side_of_page(self):
        item = block(
            "p0001-b0009",
            "3.2.1.2 称量斗支撑结构",
            "3.2.1.2 Weigh-Hopper Support Structure",
            [42.6, 279.7, 166.4, 290.1],
            size=10.5,
        )
        item["role"] = "heading-3-10.5"
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "content_bounds": [42.6, 168.5],
            "table_cells": [],
            "image_boxes": [],
            "blocks": [item],
        }
        container = rebuild.resolve_text_container(page, item, item["lines"][0])
        self.assertGreater(container[2], 500)

    def test_heading_crossing_image_moves_into_safe_band_above_image(self):
        section = block("p0001-b0009", "4. Electrical Control", "4. Electrical Control", [90, 298, 259, 314], size=16)
        section["role"] = "heading-1-16"
        heading = block("p0001-b0010", "4.1 Standard centralized control system", "4.1 Standard Centralized Control System", [122, 329, 285, 346], size=16)
        heading["role"] = "heading-2-16"
        page = {"page": 1, "width": 595.3, "height": 841.9, "content_bounds": [90, 505], "table_cells": [], "image_boxes": [[294, 340, 540, 477]], "blocks": [section, heading]}
        container = rebuild.resolve_text_container(page, heading, heading["lines"][0])
        self.assertGreater(container[2], 500)
        self.assertGreaterEqual(container[1], 316)
        self.assertLessEqual(container[3], 338)

    def test_semantic_chapter_and_section_headings_are_bold_and_larger_than_body(self):
        classify = require(pipeline, "classify_document_roles")
        chapter = block(
            "p0001-b0001", "第一章 概述", "CHAPTER 1 OVERVIEW", [250, 110, 345, 122], size=10.5
        )
        section = block(
            "p0001-b0002", "1.1 主方基本要求", "1.1 Owner Requirements", [60, 140, 190, 152], size=10.5
        )
        body_blocks = [
            block(
                f"p0001-b{index:04d}",
                "这是正文内容，用于建立同页正文基准字号。",
                "Body copy establishes the page body-size baseline.",
                [60, 180 + index * 20, 530, 192 + index * 20],
                size=10.5,
            )
            for index in range(3, 9)
        ]
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "blocks": [chapter, section, *body_blocks],
        }
        classify([page])
        body_size = body_blocks[0]["style"]["role_size"]
        for heading in (chapter, section):
            self.assertTrue(heading["role"].startswith("heading-"))
            self.assertTrue(heading["style"]["bold"])
            self.assertGreaterEqual(heading["style"]["role_size"], body_size + 1)

    def test_numbering_does_not_invent_bold_when_source_font_is_regular(self):
        classify = require(pipeline, "classify_document_roles")
        numbered = block(
            "p0001-b0001",
            "1. A normal numbered paragraph",
            "1. A normal numbered paragraph",
            [122, 100, 505, 116],
            font="ABCDEE+FangSong",
            size=16,
        )
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "blocks": [numbered],
        }
        classify([page])
        self.assertFalse(numbered["style"]["source_bold"])
        self.assertFalse(numbered["style"]["bold"])

    def test_long_numbered_body_paragraph_is_not_promoted_to_heading(self):
        classify = require(pipeline, "classify_document_roles")
        numbered = block(
            "p0001-b0001",
            "3.18.4现场仪表和组件：包括测温仪表及组件、压力仪表及组件、流量仪表及组件、称重仪表及组件、位置检测元件、料位检测组件等。",
            "3.18.4 Field instruments and components include temperature, pressure, flow, weighing, position and level devices.",
            [42.6, 700, 552, 728],
            size=10.5,
        )
        body_blocks = [
            block(f"p0001-b{index:04d}", "正文内容", "Body text", [60, 100 + index * 20, 520, 112 + index * 20], size=10.5)
            for index in range(2, 8)
        ]
        page = {"page": 1, "width": 595.3, "height": 841.9, "table_cells": [], "blocks": [numbered, *body_blocks]}
        classify([page])
        self.assertTrue(numbered["role"].startswith("body-"))
        self.assertFalse(numbered["style"]["bold"])

    def test_decimal_measurement_with_unit_is_not_promoted_to_heading(self):
        classify = require(pipeline, "classify_document_roles")
        measurement = block("p0001-b0001", "0.5mm color-coated steel sheet retains heat", "0.5 mm color-coated steel sheet retains heat", [90, 267, 422, 283], size=16)
        page = {"page": 1, "width": 595.3, "height": 841.9, "table_cells": [], "blocks": [measurement]}
        classify([page])
        self.assertTrue(measurement["role"].startswith("body-"))
        self.assertFalse(measurement["style"]["bold"])

    def test_short_line_before_numbered_list_continues_wrapped_heading(self):
        classify = require(pipeline, "classify_document_roles")
        heading = block("p0001-b0001", "4.2 PLC automatic control sys", "4.2 PLC Automatic Control", [122, 485, 285, 502], size=16)
        continuation = block("p0001-b0002", "tem (optional)", "System (Optional)", [90, 517, 202, 533], size=16)
        item = block("p0001-b0003", "1）power supply and distribution", "1) Power Supply and Distribution System", [122, 548, 274, 564], size=16)
        page = {"page": 1, "width": 595.3, "height": 841.9, "content_bounds": [90, 505], "table_cells": [], "image_boxes": [], "blocks": [heading, continuation, item]}
        classify([page])
        flows = require(rebuild, "group_paragraph_flows")(page)
        heading_flow = next(flow for flow in flows if heading["id"] in flow["block_ids"])
        self.assertEqual([heading["id"], continuation["id"]], heading_flow["block_ids"])
        self.assertEqual("4.2 PLC Automatic Control System (Optional)", heading_flow["text"])
        self.assertNotIn(item["id"], heading_flow["block_ids"])

    def test_font_family_name_alone_does_not_invent_kaiti_boldness(self):
        detect = require(pipeline, "source_font_is_bold")
        header = block(
            "p0001-b0001",
            "Running header",
            "Running header",
            [260, 45, 335, 56],
            font="ABCDEE+KaiTi",
            size=10.5,
        )
        self.assertFalse(detect(header))

    def test_explicit_source_visual_weight_override_is_respected(self):
        detect = require(pipeline, "source_font_is_bold")
        emphasis = block(
            "p0001-b0001",
            "(Patent No. ZL 2013 2 0034326.2)",
            "(Patent No. ZL 2013 2 0034326.2)",
            [90, 516, 355, 533],
            font="ABCDEE+FangSong",
            size=16,
        )
        emphasis["source_bold_override"] = True
        self.assertTrue(detect(emphasis))

    def test_body_font_is_not_promoted_to_bold_by_absolute_size(self):
        classify = require(pipeline, "classify_document_roles")
        body = block(
            "p0001-b0001",
            "body copy",
            "body copy",
            [90, 100, 505, 116],
            font="ABCDEE+FangSong",
            size=16,
        )
        heading = block(
            "p0001-b0002",
            "V. Equipment Selection",
            "V. Equipment Selection",
            [90, 650, 320, 666],
            font="ABCDEE+SimHei",
            size=16,
        )
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "blocks": [body, heading],
        }
        classify([page])
        self.assertTrue(body["role"].startswith("body-"))
        self.assertFalse(body["style"]["bold"])
        self.assertTrue(heading["role"].startswith("heading-"))
        self.assertTrue(heading["style"]["bold"])

    def test_document_body_size_is_weighted_by_reading_text_not_small_fragments(self):
        classify = require(pipeline, "classify_document_roles")
        items = [
            block(
                f"p0001-b{index:04d}",
                "Short cell",
                "Short cell",
                [40, 100 + index * 12, 120, 110 + index * 12],
                size=10.5,
            )
            for index in range(1, 11)
        ]
        body = block(
            "p0001-b0011",
            "A complete source paragraph with substantially more reading text than a cell",
            "A complete translated paragraph with substantially more reading text than a cell",
            [90, 300, 505, 316],
            size=16,
        )
        items.extend([body, dict(body, id="p0001-b0012"), dict(body, id="p0001-b0013")])
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "blocks": items,
        }
        classify([page])
        self.assertTrue(body["role"].startswith("body-"))
        self.assertFalse(body["style"]["bold"])


class AlignmentTests(unittest.TestCase):
    def test_centered_origin_uses_the_container_center(self):
        origin = require(rebuild, "horizontal_text_origin")
        self.assertAlmostEqual(250.0, origin("center", 100, 500, 100))
        self.assertAlmostEqual(100.0, origin("left", 100, 500, 100))
        self.assertAlmostEqual(400.0, origin("right", 100, 500, 100))

    def test_first_line_indent_is_not_misclassified_as_centered(self):
        infer = require(rebuild, "infer_block_alignment")
        paragraph = block(
            "p0001-b0001",
            "paragraph",
            "paragraph",
            [122, 80, 505, 96],
            align=1,
        )
        paragraph["lines"].append(
            {"text": "continuation", "bbox": [90, 111, 505, 127], "characters": [], "runs": []}
        )
        self.assertEqual("left", infer(paragraph, 595.3))

    def test_wide_symmetric_body_line_is_not_misclassified_as_centered(self):
        infer = require(rebuild, "infer_block_alignment")
        paragraph = block(
            "p0001-b0001",
            "wide paragraph line",
            "wide paragraph line",
            [90, 111, 505, 127],
            align=1,
        )
        paragraph["role"] = "body-16"
        self.assertEqual("left", infer(paragraph, 595.3))

    def test_right_side_running_header_is_right_aligned(self):
        infer = require(rebuild, "infer_block_alignment")
        header = block(
            "p0001-b0001",
            "工程技术方案",
            "Technical Proposal",
            [374, 56, 552, 66],
            size=9,
            align=0,
        )
        header["role"] = "running-header"
        self.assertEqual("right", infer(header, 595.3))


class ParagraphFlowTests(unittest.TestCase):
    def test_reviewed_flow_group_can_join_sentences_for_page_reflow(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block("p0001-b0001", "第一句。", "First sentence.", [60, 100, 520, 112], size=10.5)
        second = block("p0001-b0002", "第二句。", "Second sentence.", [60, 116, 520, 128], size=10.5)
        first["reviewed_flow_group"] = "system-description"
        second["reviewed_flow_group"] = "system-description"
        page = {"page": 1, "width": 595.3, "height": 841.9, "content_bounds": [42.6, 552.7], "table_cells": [], "image_boxes": [], "blocks": [first, second]}
        flows = group(page)
        self.assertEqual(1, len(flows))
        self.assertEqual(["p0001-b0001", "p0001-b0002"], flows[0]["block_ids"])

    def test_reviewed_text_region_adjustment_moves_block_geometry(self):
        apply_adjustments = require(rebuild, "apply_reviewed_text_region_adjustments")
        item = block("p0001-b0001", "caption", "Caption", [100, 460, 200, 472], size=10.5)
        item["characters"] = [{"text": "C", "bbox": [100, 460, 106, 472]}]
        page = {
            "page": 1,
            "blocks": [item],
            "reviewed_text_region_adjustments": [{"block_ids": ["p0001-b0001"], "dy": 50}],
            "reviewed_flow_groups": [{"id": "caption-flow", "block_ids": ["p0001-b0001"]}],
        }
        apply_adjustments([page])
        self.assertEqual([100, 510, 200, 522], item["bbox"])
        self.assertEqual([100, 510, 106, 522], item["characters"][0]["bbox"])
        self.assertEqual("caption-flow", item["reviewed_flow_group"])

    def test_dot_leader_translation_is_compacted_to_available_width(self):
        compact = require(rebuild, "compact_dot_leader_text")
        scratch = ImageDraw.Draw(Image.new("RGB", (2400, 200), "white"))
        source = "2.2 Resource balance sheet" + "." * 120 + "6"
        rendered = compact(
            scratch,
            source,
            r"C:\Windows\Fonts\arial.ttf",
            42,
            1800,
        )
        font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 42)
        self.assertTrue(rendered.startswith("2.2 Resource balance sheet"))
        self.assertTrue(rendered.endswith("6"))
        self.assertLess(rendered.count("."), source.count("."))
        self.assertLessEqual(scratch.textlength(rendered, font=font), 1800)

    def test_long_fixed_slot_flow_uses_controlled_fallback_fit(self):
        fit_flow = require(rebuild, "fit_flow_text_to_slots")
        scratch = ImageDraw.Draw(Image.new("RGB", (2400, 200), "white"))
        text = (
            "This technical paragraph preserves the complete meaning while fitting "
            "inside one fixed source line in the inspection copy."
        )
        font, lines, fallback = fit_flow(
            scratch,
            text,
            r"C:\Windows\Fonts\arial.ttf",
            42,
            [[0, 0, 340, 13]],
            minimum_scale=0.9,
        )
        self.assertTrue(fallback)
        self.assertEqual(text, " ".join(lines))
        self.assertLess(font.size, 38)

    def test_readable_body_floor_is_based_on_source_size(self):
        floor = require(rebuild, "minimum_body_font_size")
        self.assertEqual(9.5, floor({"size": 16}))
        self.assertEqual(9.5, floor({"size": 14}))

    def test_numbered_item_starts_a_new_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        intro = block(
            "p0001-b0001", "including the following", "including the following", [90, 100, 250, 116]
        )
        item = block(
            "p0001-b0002", "1、first project", "1. First project", [122, 131, 505, 147]
        )
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [90, 505],
            "blocks": [intro, item],
        }
        flows = group(page)
        self.assertEqual(2, len(flows))

    def test_fullwidth_parenthesized_number_starts_a_new_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        intro = block("p0001-b0001", "optional system", "System (Optional)", [90, 100, 250, 116])
        item = block("p0001-b0002", "1）power supply", "1) Power Supply", [122, 131, 505, 147])
        page = {"page": 1, "width": 595.3, "height": 841.9, "table_cells": [], "image_boxes": [], "content_bounds": [90, 505], "blocks": [intro, item]}
        self.assertEqual(2, len(group(page)))

    def test_fullwidth_nested_number_starts_a_new_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        parent = block("p0001-b0001", "3）distribution system", "3) Distribution System", [122, 100, 250, 116])
        nested = block("p0001-b0002", "（1）、power supply voltage", "(1) Power supply voltage", [122, 131, 505, 147])
        page = {"page": 1, "width": 595.3, "height": 841.9, "table_cells": [], "image_boxes": [], "content_bounds": [90, 505], "blocks": [parent, nested]}
        self.assertEqual(2, len(group(page)))

    def test_hierarchical_toc_entry_starts_a_new_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block(
            "p0002-b0004",
            "1.1 基本要求........................................3",
            "1.1 Basic requirements........................................3",
            [53, 125, 552, 137],
            size=10.5,
        )
        second = block(
            "p0002-b0005",
            "1.2 范围说明........................................4",
            "1.2 Scope description........................................4",
            [53, 140, 552, 152],
            size=10.5,
        )
        page = {
            "page": 2,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [42, 552],
            "blocks": [first, second],
        }
        self.assertEqual(2, len(group(page)))

    def test_compact_hierarchical_toc_entry_starts_a_new_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block(
            "p0002-b0007",
            "2.1竖窑指标........................................5",
            "2.1 Shaft-kiln indicators........................................5",
            [53, 177, 552, 189],
            size=10.5,
        )
        second = block(
            "p0002-b0008",
            "2.2资源平衡表........................................6",
            "2.2 Resource balance........................................6",
            [53, 191, 552, 203],
            size=10.5,
        )
        page = {
            "page": 2,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [42, 552],
            "blocks": [first, second],
        }
        self.assertEqual(2, len(group(page)))

    def test_decimal_continuation_does_not_start_a_new_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block("p0001-b0001", "insulation", "insulation", [90, 100, 505, 116])
        decimal = block(
            "p0001-b0002", "0.5 mm steel sheet", "0.5 mm steel sheet", [90, 131, 505, 147]
        )
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [90, 505],
            "blocks": [first, decimal],
        }
        self.assertEqual(1, len(group(page)))

    def test_semicolon_list_continues_in_the_same_paragraph_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block("p0001-b0001", "cabinet;", "cabinet;", [90, 100, 280, 116])
        second = block("p0001-b0002", "controller;", "controller;", [90, 131, 280, 147])
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [90, 505],
            "blocks": [first, second],
        }
        self.assertEqual(1, len(group(page)))

    def test_hyphen_bullets_keep_source_line_breaks(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block("p0001-b0001", "- CaO-53.05%", "- CaO-53.05%", [80, 280, 170, 292], size=10.5)
        second = block("p0001-b0002", "- MgO-1.25%", "- MgO-1.25%", [80, 303, 170, 315], size=10.5)
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [60, 530],
            "blocks": [first, second],
        }
        self.assertEqual(2, len(group(page)))

    def test_fullwidth_colon_ends_a_standalone_label_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block("p0001-b0001", "客户现有资料：", "Owner data:", [60, 230, 180, 242], size=10.5)
        second = block("p0001-b0002", "石灰石成分分析：", "Limestone analysis:", [60, 253, 190, 265], size=10.5)
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [60, 530],
            "blocks": [first, second],
        }
        self.assertEqual(2, len(group(page)))


class ProtectedNativeTextTests(unittest.TestCase):
    def test_ascii_formula_line_is_kept_and_copies_itself_as_translation(self):
        line_record = require(pipeline, "line_record")
        group_lines = require(pipeline, "group_lines")
        text = "- CaO-53.05%"
        chars = []
        for index, character in enumerate(text):
            x0 = 80 + index * 6
            chars.append(
                {
                    "text": character,
                    "x0": x0,
                    "x1": x0 + 5,
                    "top": 280,
                    "bottom": 291,
                    "size": 10.5,
                    "width": 5,
                    "fontname": "ABCDEE+SimSun",
                    "non_stroking_color": [0, 0, 0],
                    "matrix": [1, 0, 0, 1, 0, 0],
                }
            )
        record = line_record(
            {"chars": chars, "x0": 80, "x1": 80 + len(text) * 6, "top": 280, "bottom": 291},
            595.3,
        )
        self.assertIsNotNone(record)
        grouped = group_lines([record], 595.3)
        self.assertEqual(text, grouped[0]["source_text"])
        self.assertEqual(text, grouped[0]["translation"])

    def test_wide_body_line_near_table_is_not_treated_as_table_note(self):
        near = require(rebuild, "_near_table_region")
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [{"bbox": [40, 262, 560, 400]}],
        }
        self.assertFalse(near(page, [90, 205, 442, 221], 16))
        self.assertTrue(near(page, [482, 225, 555, 236], 10.5))

    def test_flow_does_not_add_continuation_slot_through_wide_image(self):
        group = require(rebuild, "group_paragraph_flows")
        first = block("p0001-b0001", "first", "first translated line", [90, 300, 505, 316])
        last = block("p0001-b0002", "last", "last translated line", [90, 330, 300, 346])
        heading = block("p0001-b0003", "heading", "Heading", [90, 650, 250, 666], font="ABCDEE+SimHei")
        heading["role"] = "heading-1-16"
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [[90, 354, 505, 647]],
            "content_bounds": [90, 505],
            "blocks": [first, last, heading],
        }
        flows = group(page)
        self.assertEqual(1, len(flows))
        self.assertEqual(2, len(flows[0]["slots"]))

    def test_centered_cover_metadata_is_not_merged_as_a_body_paragraph(self):
        group = require(rebuild, "group_paragraph_flows")
        company = block("p0001-b0001", "Company", "Company Name Ltd.", [190, 670, 405, 686], align=1)
        date = block("p0001-b0002", "Date", "August 2026", [240, 705, 355, 721], align=1)
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [90, 505],
            "blocks": [company, date],
        }
        self.assertEqual([], group(page))
        box = rebuild.resolve_text_container(page, company, company["lines"][0])
        self.assertLessEqual(box[0], 24)
        self.assertGreaterEqual(box[2], 570)

    def test_narrow_text_immediately_above_a_table_uses_table_layout_not_body_flow(self):
        group = require(rebuild, "group_paragraph_flows")
        item = block(
            "p0001-b0001",
            "custom note",
            "Customized according to material characteristics",
            [481, 75, 555, 86],
            size=10.5,
        )
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [{"bbox": [475, 104, 562, 151]}],
            "image_boxes": [],
            "content_bounds": [33, 562],
            "blocks": [item],
        }
        self.assertEqual([], group(page))
        container = rebuild.resolve_text_container(page, item, item["lines"][0])
        self.assertGreaterEqual(container[3], 100)

    def test_adjacent_source_lines_form_one_flow_with_image_avoidance_slots(self):
        group = require(rebuild, "group_paragraph_flows")
        blocks = [
            block("p0001-b0001", "first", "The first translated fragment", [122, 80, 505, 96]),
            block("p0001-b0002", "second", "continues beside the image", [90, 111, 290, 127]),
            block("p0001-b0003", "final.", "and ends after the image.", [90, 142, 505, 158]),
        ]
        page = {
            "page": 1,
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [[330, 100, 520, 140]],
            "blocks": blocks,
        }
        flows = group(page)
        self.assertEqual(1, len(flows))
        self.assertEqual(3, len(flows[0]["slots"]))
        self.assertLessEqual(flows[0]["slots"][1][2], 324)
        self.assertGreaterEqual(flows[0]["slots"][2][2], 500)

    def test_flow_fitting_uses_one_font_size_for_the_entire_paragraph(self):
        fit = require(rebuild, "fit_text_to_slots")
        image = Image.new("RGB", (8, 8), "white")
        draw = ImageDraw.Draw(image)
        slots = [[0, 0, 180, 24], [0, 30, 110, 54], [0, 60, 180, 84]]
        font, lines, _ = fit(
            draw,
            "one professional paragraph must use a single consistent size across every line",
            r"C:\Windows\Fonts\arial.ttf",
            16 * rebuild.LAYOUT_SCALE,
            slots,
            minimum_scale=0.55,
        )
        self.assertLessEqual(len(lines), len(slots))
        self.assertEqual(
            "one professional paragraph must use a single consistent size across every line",
            " ".join(lines),
        )
        self.assertGreater(font.size, 0)

    def test_same_body_role_uses_one_page_level_font_size(self):
        harmonize = require(rebuild, "harmonize_flow_font_sizes")
        image = Image.new("RGB", (8, 8), "white")
        draw = ImageDraw.Draw(image)
        style = block("x", "x", "x", [0, 0, 100, 20])["style"]
        flows = [
            {
                "id": "short",
                "role": "body-16",
                "text": "short paragraph",
                "style": dict(style),
                "slots": [[0, 0, 200, 24]],
            },
            {
                "id": "long",
                "role": "body-16",
                "text": "a longer paragraph needs more words to fit inside the same source line slots",
                "style": dict(style),
                "slots": [[0, 0, 200, 24], [0, 30, 200, 54]],
            },
        ]
        harmonize(flows, pipeline, draw)
        self.assertEqual(flows[0]["target_font_size"], flows[1]["target_font_size"])
        self.assertGreaterEqual(flows[0]["target_font_size"], 11.5)

    def test_harmonization_defers_an_unfittable_flow_to_the_readable_fit_stage(self):
        harmonize = require(rebuild, "harmonize_flow_font_sizes")
        image = Image.new("RGB", (8, 8), "white")
        draw = ImageDraw.Draw(image)
        style = block("x", "x", "x", [0, 0, 100, 20])["style"]
        flows = [{
            "id": "too-long",
            "role": "body-16",
            "text": "very long " * 200,
            "style": dict(style),
            "slots": [[0, 0, 60, 20]],
        }]
        harmonize(flows, pipeline, draw)
        self.assertIn("target_font_size", flows[0])

    def test_page_uniform_body_override_sets_one_fixed_flow_size(self):
        harmonize = require(rebuild, "harmonize_flow_font_sizes")
        image = Image.new("RGB", (8, 8), "white")
        draw = ImageDraw.Draw(image)
        style = block("x", "x", "x", [0, 0, 100, 20])["style"]
        flows = [
            {"id": "a", "role": "body-16", "text": "short", "style": dict(style), "slots": [[0, 0, 200, 24]]},
            {"id": "b", "role": "body-16", "text": "longer body text", "style": dict(style), "slots": [[0, 0, 200, 24]]},
        ]
        harmonize(flows, pipeline, draw, uniform_body_font_size=8.0)
        self.assertEqual([8.0, 8.0], [flow["target_font_size"] for flow in flows])
        self.assertTrue(all(flow["fixed_body_font_size"] for flow in flows))


class ContainerTests(unittest.TestCase):
    def test_header_container_keeps_enough_height_for_source_font_size(self):
        resolve = require(rebuild, "resolve_text_container")
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [],
            "content_bounds": [90, 505],
        }
        item = block(
            "p0001-b0001", "header", "header", [260, 45, 335, 56], size=10.5
        )
        item["role"] = "running-header"
        box = resolve(page, item, item["lines"][0])
        self.assertGreaterEqual(box[3] - box[1], 10.5 * 1.5)

    def test_segmented_and_fragmented_blocks_in_same_cell_merge_into_one_flow(self):
        merge = require(rebuild, "merge_table_cell_flows")
        flows = [
            {
                "id": "cell:a+c",
                "block_ids": ["a", "c"],
                "text": "Uses a cabinet and protection.",
                "box": [280, 330, 470, 405],
                "source_top": 331,
                "style": {"size": 10, "color_rgb": [0, 0, 0]},
                "role": "table-10",
                "alignment": "left",
            },
            {
                "id": "cell:b",
                "block_ids": ["b"],
                "text": "Variable-frequency drives and relays.",
                "box": [280, 330, 470, 405],
                "source_top": 363,
                "style": {"size": 10, "color_rgb": [0, 0, 0]},
                "role": "table-10",
                "alignment": "left",
            },
        ]
        merged = merge(flows)
        self.assertEqual(1, len(merged))
        self.assertEqual(["a", "c", "b"], merged[0]["block_ids"])
        self.assertIn("Variable-frequency", merged[0]["text"])

    def test_fragments_just_above_detected_table_border_share_a_synthetic_cell(self):
        synthetic = require(rebuild, "pretable_cell_box")
        first = block("p0001-b0001", "first", "Customized according to", [482, 75, 555, 86], size=10.5)
        second = block("p0001-b0002", "second", "material characteristics", [508, 91, 529, 101], size=10.5)
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [
                {"bbox": [475, 106, 562, 150]},
                {"bbox": [475, 150, 562, 220]},
                {"bbox": [475, 220, 562, 290]},
            ],
            "blocks": [first, second],
        }
        self.assertEqual(
            synthetic(page, first["bbox"]), synthetic(page, second["bbox"])
        )

    def test_cross_cell_fragments_are_aggregated_once_per_physical_cell(self):
        aggregate = require(rebuild, "aggregate_table_fragments")
        fragments = [
            {
                "block_id": "p0001-b0001",
                "text": "Uses internal lifting flights",
                "box": [280, 402, 470, 520],
                "source_top": 410,
                "source_left": 285,
                "style": {"size": 10, "color_rgb": [0, 0, 0]},
                "role": "body-10",
            },
            {
                "block_id": "p0001-b0002",
                "text": "5",
                "box": [60, 402, 105, 520],
                "source_top": 452,
                "source_left": 70,
                "style": {"size": 10, "color_rgb": [0, 0, 0]},
                "role": "body-10",
            },
            {
                "block_id": "p0001-b0002",
                "text": "and advances in a spiral path",
                "box": [280, 402, 470, 520],
                "source_top": 452,
                "source_left": 286,
                "style": {"size": 10, "color_rgb": [0, 0, 0]},
                "role": "body-10",
            },
        ]
        flows = aggregate(fragments)
        self.assertEqual(2, len(flows))
        technical = next(flow for flow in flows if flow["box"][0] == 280)
        self.assertEqual(
            "Uses internal lifting flights and advances in a spiral path",
            technical["text"],
        )
        self.assertEqual(
            ["p0001-b0001", "p0001-b0002"], technical["block_ids"]
        )

    def test_vertical_fragments_in_one_table_cell_become_one_cell_flow(self):
        group = require(rebuild, "group_table_cell_flows")
        first = block("p0001-b0001", "part one", "Discharge", [67, 409, 99, 420], size=10.5)
        second = block("p0001-b0002", "part two", "System", [78, 425, 89, 435], size=10.5)
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [{"bbox": [60.5, 398.3, 106.3, 445.6]}],
            "image_boxes": [],
            "content_bounds": [33, 562],
            "blocks": [first, second],
        }
        flows = group(page)
        self.assertEqual(1, len(flows))
        self.assertEqual("Discharge System", flows[0]["text"])
        self.assertEqual([63.5, 400.3, 103.3, 443.6], flows[0]["box"])

    def test_footer_container_ignores_nearby_logo_image(self):
        resolve = require(rebuild, "resolve_text_container")
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [],
            "image_boxes": [[90, 775, 110, 795]],
            "content_bounds": [90, 505],
        }
        item = block("p0001-b0001", "footer", "footer", [103, 780, 499, 791])
        item["role"] = "footer"
        box = resolve(page, item, item["lines"][0])
        self.assertLessEqual(box[0], 24)
        self.assertGreaterEqual(box[2], 570)

    def test_table_text_uses_the_cell_not_the_page_right_edge(self):
        resolve = require(rebuild, "resolve_text_container")
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [{"bbox": [280, 100, 470, 180]}],
            "image_boxes": [],
            "content_bounds": [90, 505],
        }
        item = block("p0001-b0001", "cell", "cell text", [284, 110, 410, 125])
        box = resolve(page, item, item["lines"][0])
        self.assertGreaterEqual(box[0], 280)
        self.assertLessEqual(box[2], 470)

    def test_persistent_table_column_boundary_overrides_a_merged_detected_cell(self):
        interval = require(rebuild, "table_column_interval")
        page = {
            "width": 595.3,
            "height": 841.9,
            "table_cells": [
                {"bbox": [280, 100, 540, 150]},
                {"bbox": [280, 150, 470, 220]},
                {"bbox": [470, 150, 540, 220]},
                {"bbox": [280, 220, 470, 290]},
                {"bbox": [470, 220, 540, 290]},
                {"bbox": [280, 290, 470, 360]},
                {"bbox": [470, 290, 540, 360]},
            ],
        }
        self.assertEqual([280.0, 470.0], interval(page, [284, 110, 430, 125]))
        self.assertIsNone(interval(page, [440, 110, 500, 125]))

    def test_dense_cell_text_shrinks_uniformly_instead_of_crossing_border(self):
        fit = require(rebuild, "fit_text_to_slots")
        image = Image.new("RGB", (8, 8), "white")
        draw = ImageDraw.Draw(image)
        slots = [[0, 0, 85, 18], [0, 20, 85, 38], [0, 40, 85, 58]]
        font, lines, _ = fit(
            draw,
            "Oversize equipment is fabricated and assembled on site",
            r"C:\Windows\Fonts\arial.ttf",
            12 * rebuild.LAYOUT_SCALE,
            slots,
            minimum_scale=0.35,
        )
        self.assertLess(font.size, round(12 * rebuild.LAYOUT_SCALE))
        for line, slot in zip(lines, slots):
            self.assertLessEqual(draw.textlength(line, font=font), (slot[2] - slot[0]) * rebuild.LAYOUT_SCALE)

    def test_box_fit_uses_exact_line_metrics_for_vertical_containment(self):
        image = Image.new("RGB", (8, 8), "white")
        draw = ImageDraw.Draw(image)
        text = " ".join(["technicalword"] * 40)
        height = 148 * rebuild.LAYOUT_SCALE
        font, rendered, spacing = pipeline.fit_text(
            draw,
            text,
            r"C:\Windows\Fonts\arial.ttf",
            10 * rebuild.LAYOUT_SCALE,
            185 * rebuild.LAYOUT_SCALE,
            height,
            minimum_scale=0.35,
        )
        ascent, descent = font.getmetrics()
        lines = rendered.splitlines()
        exact_height = len(lines) * (ascent + descent) + max(0, len(lines) - 1) * spacing
        self.assertLessEqual(exact_height, height)


if __name__ == "__main__":
    unittest.main()
