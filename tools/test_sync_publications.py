#!/usr/bin/env python3
"""
Offline unit tests for sync_publications.py. No network access is used.

Run with:
    python3 -m unittest tools/test_sync_publications.py
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_publications as sp

ROOT = Path(__file__).resolve().parent.parent


class TestRoundTrip(unittest.TestCase):
    def test_dumps_publications_matches_file_byte_for_byte(self):
        raw = sp.DEFAULT_DATA.read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertEqual(sp.dumps_publications(data), raw)

    def test_validate_publications_on_real_file_is_clean(self):
        data = json.loads(sp.DEFAULT_DATA.read_text(encoding="utf-8"))
        self.assertEqual(sp.validate_publications(data), [])

    def test_programmes_match_main_js(self):
        js = (ROOT / "assets" / "js" / "main.js").read_text(encoding="utf-8")
        match = re.search(r"var PROGRAMMES = \{(.*?)\};", js, re.DOTALL)
        self.assertIsNotNone(match, "could not find PROGRAMMES block in main.js")
        keys = tuple(re.findall(r'"([a-z0-9-]+)":', match.group(1)))
        self.assertEqual(keys, sp.PROGRAMMES)


class TestSameWork(unittest.TestCase):
    def test_identical_titles_match(self):
        self.assertTrue(sp.same_work("mna net a segmentation model", "mna net a segmentation model"))

    def test_containment_with_prefix_matches(self):
        short = sp.normalise_title("MNA-Net: A segmentation model for brain tumours in MRI scans")
        long_ = sp.normalise_title("MNA-Net: A segmentation model for brain tumours in MRI scans (extended)")
        self.assertTrue(sp.same_work(short, long_))

    def test_short_strings_do_not_falsely_match(self):
        self.assertFalse(sp.same_work("eye", "eye health study of glaucoma patients in australia"))

    def test_unrelated_titles_do_not_match(self):
        a = sp.normalise_title("A deep learning approach to glaucoma detection using fundus images")
        b = sp.normalise_title("Coronary artery calcification scoring with convolutional networks")
        self.assertFalse(sp.same_work(a, b))

    def test_empty_strings_never_match(self):
        self.assertFalse(sp.same_work("", ""))
        self.assertFalse(sp.same_work("something", ""))


class TestGuessType(unittest.TestCase):
    def test_lncs_book_chapter_becomes_conference(self):
        work = {
            "type": "book-chapter",
            "doi": "10.1007/978-3-031-12345-6_7",
            "primary_location": {"source": {"type": "book series", "display_name": "Lecture Notes in Computer Science"}},
            "locations": [],
        }
        self.assertEqual(sp.guess_type(work), "conference")

    def test_arxiv_doi_becomes_preprint(self):
        work = {"type": "article", "doi": "10.48550/arXiv.2501.01234", "primary_location": {}, "locations": []}
        self.assertEqual(sp.guess_type(work), "preprint")

    def test_research_square_doi_becomes_preprint(self):
        work = {"type": "preprint", "doi": "10.21203/rs.3.rs-11205011/v1", "primary_location": {}, "locations": []}
        self.assertEqual(sp.guess_type(work), "preprint")

    def test_plain_article_becomes_journal(self):
        work = {
            "type": "article",
            "doi": "10.1016/j.media.2023.102845",
            "primary_location": {"source": {"type": "journal", "display_name": "Medical Image Analysis"}},
            "locations": [],
        }
        self.assertEqual(sp.guess_type(work), "journal")

    def test_conference_name_without_source_type_still_detected(self):
        work = {
            "type": "article",
            "doi": "10.1109/something.2023.123",
            "primary_location": {"source": {"type": "journal", "display_name": "Proceedings of CVPR 2023"}},
            "locations": [],
        }
        self.assertEqual(sp.guess_type(work), "conference")


class TestSuggestProgrammes(unittest.TestCase):
    def test_brain_tumour_gives_cancer_only(self):
        tags = sp.suggest_programmes("MNA-Net: segmentation of brain tumours in MRI")
        self.assertEqual(tags, ["cancer-imaging-precision-oncology"])

    def test_alzheimer_gives_brain(self):
        tags = sp.suggest_programmes("Predicting Alzheimer's disease progression from brain MRI")
        self.assertIn("brain-cognition", tags)

    def test_visual_field_gives_vision(self):
        tags = sp.suggest_programmes("Deep learning for visual field defect detection in glaucoma")
        self.assertEqual(tags, ["vision-eye-health-oculomics"])

    def test_mining_gives_none(self):
        tags = sp.suggest_programmes("Ore grade estimation using convolutional neural networks")
        self.assertEqual(tags, [])

    def test_cancer_and_cognition_without_strong_cognition_word_drops_cognition(self):
        tags = sp.suggest_programmes("Segmentation of brain tumours using a U-Net architecture")
        self.assertEqual(tags, ["cancer-imaging-precision-oncology"])

    def test_cancer_and_strong_cognition_word_keeps_both(self):
        tags = sp.suggest_programmes("Neuroimaging of brain tumours and dementia comorbidity")
        self.assertIn("cancer-imaging-precision-oncology", tags)
        self.assertIn("brain-cognition", tags)


class TestBuildAuthors(unittest.TestCase):
    def _work_with_authors(self, names, member_orcids=()):
        authorships = []
        for name in names:
            orcid = member_orcids.get(name) if isinstance(member_orcids, dict) else None
            authorships.append({"author": {"display_name": name, "orcid": f"https://orcid.org/{orcid}" if orcid else None}})
        return {"authorships": authorships}

    def test_small_author_list_kept_in_full(self):
        names = ["A One", "B Two", "C Three"]
        work = self._work_with_authors(names)
        people = sp.build_authors(work)
        self.assertEqual([p["name"] for p in people], names)

    def test_large_author_list_trimmed_to_first_three_plus_members_plus_et_al(self):
        names = [f"Author {i}" for i in range(1, 11)]
        member_orcids = {"Author 7": sp.AUTHORS[0]["orcid"]}
        work = self._work_with_authors(names, member_orcids)
        people = sp.build_authors(work)
        self.assertEqual(people[0]["name"], "Author 1")
        self.assertEqual(people[1]["name"], "Author 2")
        self.assertEqual(people[2]["name"], "Author 3")
        self.assertEqual(people[-1]["name"], "et al.")
        member_names = [p["name"] for p in people if p.get("groupMember")]
        self.assertIn("Author 7", member_names)

    def test_group_member_flagged_by_name_match(self):
        work = self._work_with_authors(["Naeha Sharif", "Someone Else"])
        people = sp.build_authors(work)
        sharif = next(p for p in people if p["name"] == "Naeha Sharif")
        self.assertTrue(sharif.get("groupMember"))
        other = next(p for p in people if p["name"] == "Someone Else")
        self.assertNotIn("groupMember", other)

    def test_group_member_flagged_by_orcid_match(self):
        work = self._work_with_authors(
            ["Ghulam Mubashar Hassan", "Someone Else"],
            {"Ghulam Mubashar Hassan": sp.AUTHORS[0]["orcid"]},
        )
        people = sp.build_authors(work)
        hassan = next(p for p in people if p["name"] == "Ghulam Mubashar Hassan")
        self.assertTrue(hassan.get("groupMember"))


class TestVersionCollapse(unittest.TestCase):
    def _candidate(self, title, year, is_preprint, wid):
        work = {
            "title": title,
            "publication_year": year,
            "type": "preprint" if is_preprint else "article",
            "doi": "10.48550/arXiv.2501.00001" if is_preprint else "10.1016/j.media.2025.000001",
            "primary_location": {},
            "locations": [],
            "id": f"https://openalex.org/{wid}",
            "authorships": [],
            "best_oa_location": {},
        }
        key = sp.normalise_title(title)
        return {"wid": wid, "work": work, "via": ["Test Author"], "key": key, "also": []}

    def test_published_version_preferred_over_preprint(self):
        title = "D3Seg: a diffusion based segmentation model for pancreatic tumours"
        preprint = self._candidate(title, 2025, True, "W1")
        published = self._candidate(title, 2026, False, "W2")
        pool = [preprint, published]
        pool.sort(key=lambda c: (sp.guess_type(c["work"]) == "preprint", -c["work"]["publication_year"]))
        kept: list[dict] = []
        for candidate in pool:
            twin = next((k for k in kept if sp.same_work(candidate["key"], k["key"])), None)
            if twin:
                twin["also"].append(candidate["wid"])
            else:
                kept.append(candidate)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["wid"], "W2")
        self.assertIn("W1", kept[0]["also"])


class TestMisc(unittest.TestCase):
    def test_norm_doi_extracts_and_lowercases(self):
        self.assertEqual(sp.norm_doi("https://doi.org/10.1016/J.MEDIA.2023.102845"), "10.1016/j.media.2023.102845")
        self.assertIsNone(sp.norm_doi("not a doi"))
        self.assertIsNone(sp.norm_doi(None))

    def test_short_id_extracts_w_number(self):
        self.assertEqual(sp.short_id("https://openalex.org/W1234567890"), "W1234567890")
        self.assertEqual(sp.short_id(None), "")

    def test_clean_title_strips_markup_and_entities(self):
        self.assertEqual(sp.clean_title("A study of <i>&alpha;</i>-synuclein &amp; MRI"), "A study of α-synuclein & MRI")

    def test_repeated_venue_name_is_collapsed(self):
        doubled = ("IEEE Computer Society Conference on Computer Vision and Pattern Recognition/Proceedings - "
                   "IEEE Computer Society Conference on Computer Vision and Pattern Recognition/Proceedings")
        self.assertEqual(
            sp._dedupe_venue(doubled),
            "IEEE Computer Society Conference on Computer Vision and Pattern Recognition/Proceedings",
        )
        self.assertEqual(sp._dedupe_venue("Medical Image Analysis"), "Medical Image Analysis")
        self.assertEqual(
            sp._dedupe_venue("European Conference on Computer Vision - ECCV 2024"),
            "European Conference on Computer Vision - ECCV 2024",
        )

    def test_pancreas_prostate_radiotherapy_are_oncology(self):
        for title in ("Pancreas segmentation in CT scans", "Prostate lesion detection",
                      "Robust optimisation for photon radiotherapy"):
            self.assertEqual(sp.suggest_programmes(title), ["cancer-imaging-precision-oncology"], title)

    def test_make_slug_avoids_collisions(self):
        taken = {"study-something-2024"}
        slug = sp.make_slug("A study of something", 2024, taken)
        self.assertEqual(slug, "study-something-2024-2")


if __name__ == "__main__":
    unittest.main()
