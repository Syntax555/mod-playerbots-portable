"""Publication lifecycle tests; no network access or GitHub credentials required."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_latest as publisher


SHA = "a" * 40
OLDER_SHA = "b" * 40
NEWER_SHA = "c" * 40
# A main head after a force-push that dropped SHA.
FORCED_SHA = "d" * 40
# A former main commit that was removed from main's history.
REWRITTEN_SHA = "e" * 40
# A side branch commit and the merge that brings it and SHA into main.
SIDE_SHA = "f" * 40
MERGE_SHA = "1" * 40
REPOSITORY = "owner/mod-playerbots-portable"
# Shared with the server ZIP check and the launcher updater.
UNMANAGED_PATHS = json.loads(Path(__file__).with_name("unmanaged-paths.json").read_text(encoding="utf-8"))


class FakeGitHub:
    repository = REPOSITORY

    def __init__(self):
        self.calls = []
        self.main_values = [SHA]
        self.parents = {
            OLDER_SHA: [], SHA: [OLDER_SHA], NEWER_SHA: [SHA], FORCED_SHA: [OLDER_SHA],
            REWRITTEN_SHA: [OLDER_SHA], SIDE_SHA: [OLDER_SHA], MERGE_SHA: [SHA, SIDE_SHA],
        }
        # Raw compare responses keyed by (base, head) override the history.
        self.comparisons = {}
        self.fail_upload = None
        self.fail_promotion = False
        self.fail_tag_move = False
        # Numbers of the retag_release calls that fail (1 is the first call).
        self.fail_retags = set()
        self.corrupt_digest = False
        self.omit_digest = False
        self.corrupt_public = False
        self.releases = {
            1: {"id": 1, "tag_name": "latest", "name": "Latest", "draft": False},
            4: {"id": 4, "tag_name": "preview", "draft": False},
            # Left by interrupted publications.
            5: {"id": 5, "tag_name": "build-99-0123456789ab", "name": "Latest", "draft": True},
            8: {"id": 8, "tag_name": "latest-previous-77-0123456789ab", "name": "Latest", "draft": False},
            # Maintainer releases that merely resemble staging names.
            6: {"id": 6, "tag_name": "build-notes", "draft": False},
            7: {"id": 7, "tag_name": "maintainer-draft", "draft": True},
            9: {"id": 9, "tag_name": "build-12-0123456789ab", "name": "Latest", "draft": False},
        }
        self.tags = {
            "latest": OLDER_SHA, "v1.0.16": OLDER_SHA, "preview": OLDER_SHA, "build-notes": OLDER_SHA,
            "build-preserve-me": OLDER_SHA, "latest-previous-77-0123456789ab": OLDER_SHA,
        }
        self.staging_leftovers = {5, 8}
        self.draft_id = 100
        self.upload_count = 0
        self.retag_count = 0

    @property
    def writes(self):
        return [call for call in self.calls if call[0] in {
            "create_draft", "upload_asset", "delete_release", "set_tag", "delete_tag", "promote_release",
            "retag_release", "return_to_draft",
        }]

    def claim_tag(self, release_id, tag):
        # GitHub allows one published release per tag.
        if any(release["id"] != release_id and release.get("tag_name") == tag and release.get("draft") is False
               for release in self.releases.values()):
            raise publisher.APIError(422, "tag_name already_exists")

    def main_sha(self):
        self.calls.append(("main_sha",))
        if len(self.main_values) > 1:
            return self.main_values.pop(0)
        return self.main_values[0]

    def history(self, commit):
        seen, pending = set(), [commit]
        while pending:
            current = pending.pop()
            if current not in seen:
                seen.add(current)
                pending.extend(self.parents.get(current, []))
        return seen

    def compare_commits(self, base, head):
        self.calls.append(("compare_commits", base, head))
        if (base, head) in self.comparisons:
            return copy.deepcopy(self.comparisons[(base, head)])
        base_history, head_history = self.history(base), self.history(head)
        common = base_history & head_history
        merge_base = max(common, key=lambda commit: len(self.history(commit))) if common else None
        ahead, behind = len(head_history - base_history), len(base_history - head_history)
        status = ("identical" if not ahead and not behind else "ahead" if not behind
                  else "behind" if not ahead else "diverged")
        return {"status": status, "merge_base_commit": {"sha": merge_base},
                "ahead_by": ahead, "behind_by": behind}

    def create_draft(self, tag, sha, notes):
        self.calls.append(("create_draft", tag, sha, notes))
        self.releases[self.draft_id] = {
            "id": self.draft_id, "tag_name": tag, "target_commitish": sha, "name": "Latest",
            "body": notes, "draft": True, "prerelease": False, "assets": [],
            "html_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
        }
        self.tags[tag] = sha
        return copy.deepcopy(self.releases[self.draft_id])

    def upload_asset(self, release, asset):
        self.upload_count += 1
        self.calls.append(("upload_asset", asset.name))
        if self.fail_upload == self.upload_count:
            raise publisher.APIError(502, "upload failed")
        uploaded = {
            "name": asset.name, "size": asset.size, "state": "uploaded",
            "digest": None if self.omit_digest else "sha256:" + asset.sha256,
        }
        if self.corrupt_digest:
            uploaded["digest"] = "sha256:" + "0" * 64
        self.releases[release["id"]]["assets"].append(uploaded)
        return uploaded

    def get_release(self, release_id):
        self.calls.append(("get_release", release_id))
        release = copy.deepcopy(self.releases[release_id])
        if self.corrupt_public and release["draft"] is False:
            release["assets"] = release["assets"][:-1]
        return release

    def release_by_tag(self, tag):
        self.calls.append(("release_by_tag", tag))
        return next((copy.deepcopy(release) for release in self.releases.values()
                     if release.get("tag_name") == tag), None)

    def delete_release(self, release_id):
        self.calls.append(("delete_release", release_id))
        del self.releases[release_id]

    def set_tag(self, tag, sha):
        self.calls.append(("set_tag", tag, sha))
        if self.fail_tag_move and sha != OLDER_SHA:
            raise publisher.APIError(502, "tag move failed")
        self.tags[tag] = sha

    def tag_sha(self, tag):
        self.calls.append(("tag_sha", tag))
        return self.tags.get(tag)

    def delete_tag(self, tag):
        self.calls.append(("delete_tag", tag))
        self.tags.pop(tag, None)

    def promote_release(self, release_id, sha, notes):
        self.calls.append(("promote_release", release_id, sha, notes))
        if self.fail_promotion:
            raise publisher.APIError(502, "promotion failed")
        self.claim_tag(release_id, "latest")
        self.releases[release_id].update({
            "tag_name": "latest", "target_commitish": sha, "name": "Latest",
            "body": notes, "draft": False, "prerelease": False,
            "html_url": f"https://github.com/{REPOSITORY}/releases/tag/latest",
        })

    def retag_release(self, release_id, tag, sha, make_latest=False):
        self.retag_count += 1
        self.calls.append(("retag_release", release_id, tag, sha, make_latest))
        if self.retag_count in self.fail_retags:
            raise publisher.APIError(502, "release update failed")
        self.claim_tag(release_id, tag)
        self.releases[release_id]["tag_name"] = tag
        if tag not in self.tags:
            self.tags[tag] = sha

    def return_to_draft(self, release_id, tag):
        self.calls.append(("return_to_draft", release_id, tag))
        self.releases[release_id].update({"tag_name": tag, "draft": True})

    def list_releases(self):
        self.calls.append(("list_releases",))
        return copy.deepcopy(list(self.releases.values()))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for filename, required in publisher.ZIP_CONTENTS.items():
            # Download-artifact normally puts each job in a separate directory.
            artifact_dir = self.directory / filename.removesuffix(".zip")
            artifact_dir.mkdir()
            with zipfile.ZipFile(artifact_dir / filename, "w") as archive:
                for entry in required:
                    content = f"test payload: {entry}"
                    if entry == "portable-release.json":
                        content = json.dumps({"schema": 1, "revision": SHA,
                                              "package": publisher.SERVER_PACKAGE_NAME, "version": "latest"})
                    archive.writestr(entry, content)
                if filename == publisher.SERVER_PACKAGE_NAME:
                    for entry in ("configs/worldserver.conf.dist", "src/data/sql/base/db_auth/base.sql",
                                  "docs/era-talents.md", "licenses/module/COPYING", "mysql/bin/library.dll"):
                        archive.writestr(entry, f"runtime payload: {entry}")
                    archive.writestr("licenses/empty.txt", b"")
        self.notes = self.directory / "notes.md"
        self.notes.write_text(
            "Download Latest from {repository_url}. Source: {source_url}. "
            "Build [{revision}]({commit_url}).\n", encoding="utf-8",
        )
        self.client = FakeGitHub()

    def publish(self):
        return publisher.publish(self.client, SHA, self.directory, self.notes, "123456")

    def rewrite_server(self, replacements=None, extra=None, prefix=""):
        path = next(self.directory.rglob(publisher.SERVER_PACKAGE_NAME))
        with zipfile.ZipFile(path) as archive:
            files = {entry.filename: archive.read(entry) for entry in archive.infolist()}
        files.update(replacements or {})
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(prefix + name, content)
            for name, content in (extra or {}).items():
                archive.writestr(name, content)
        return path

    def test_missing_artifact_fails_before_api_writes(self):
        next(self.directory.rglob("EraTalents-client-latest.zip")).unlink()
        with self.assertRaisesRegex(publisher.PublishError, "Expected exactly one artifact"):
            self.publish()
        self.assertEqual([], self.client.calls)
        self.assertFalse((self.directory / publisher.CHECKSUM_NAME).exists())

    def test_corrupt_zip_fails_before_api_writes(self):
        next(self.directory.rglob("MultiBot-Chatless-latest.zip")).write_bytes(b"not a zip")
        with self.assertRaisesRegex(publisher.PublishError, "not a readable ZIP"):
            self.publish()
        self.assertEqual([], self.client.writes)

    def test_zip_missing_required_content_is_rejected(self):
        filename = next(self.directory.rglob("mod-playerbots-portable-latest.zip"))
        with zipfile.ZipFile(filename, "w") as archive:
            archive.writestr("readme.txt", "wrong package")
        with self.assertRaisesRegex(publisher.PublishError, "missing startup.exe"):
            self.publish()
        self.assertEqual([], self.client.writes)

    def test_duplicate_artifact_is_rejected(self):
        filename = next(self.directory.rglob("EraTalents-client-latest.zip"))
        (self.directory / filename.name).write_bytes(filename.read_bytes())
        with self.assertRaisesRegex(publisher.PublishError, "found 2"):
            self.publish()
        self.assertEqual([], self.client.writes)

    def assert_skipped_without_writes(self):
        self.assertTrue(self.publish().skipped)
        self.assertEqual([], self.client.writes)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])
        self.assertIn(1, self.client.releases)

    def test_build_missing_from_main_history_makes_no_api_writes(self):
        # Main moved back before the build, or a force-push dropped it.
        for head in (OLDER_SHA, FORCED_SHA):
            with self.subTest(head=head):
                self.client = FakeGitHub()
                self.client.main_values = [head]
                self.assert_skipped_without_writes()

    def test_main_head_replaces_older_latest(self):
        self.assertFalse(self.publish().skipped)
        self.assertEqual(SHA, self.client.tags["latest"])
        self.assertEqual([("compare_commits", OLDER_SHA, SHA)] * 3,
                         [call for call in self.client.calls if call[0] == "compare_commits"])

    def test_build_with_newer_main_commits_still_replaces_older_latest(self):
        self.client.main_values = [NEWER_SHA]
        result = self.publish()
        self.assertFalse(result.skipped)
        self.assertEqual(SHA, self.client.tags["latest"])
        release = self.client.releases[self.client.draft_id]
        self.assertEqual(SHA, release["target_commitish"])
        self.assertIn(f"https://github.com/{REPOSITORY}/blob/{SHA}", release["body"])
        self.assertNotIn(NEWER_SHA, release["body"])
        manifest = json.loads((self.directory / publisher.UPDATE_MANIFEST_NAME).read_text())
        self.assertEqual(SHA, manifest["revision"])
        self.assertEqual(3, self.client.calls.count(("compare_commits", SHA, NEWER_SHA)))

    def test_build_older_than_latest_makes_no_api_writes(self):
        self.client.main_values = [NEWER_SHA]
        self.client.tags["latest"] = NEWER_SHA
        self.assertTrue(self.publish().skipped)
        self.assertEqual([], self.client.writes)
        self.assertEqual(NEWER_SHA, self.client.tags["latest"])
        self.assertIn(1, self.client.releases)

    def test_same_commit_is_published_again(self):
        self.client.tags["latest"] = SHA
        self.assertFalse(self.publish().skipped)
        self.assertEqual(SHA, self.client.tags["latest"])
        self.assertFalse(any(call[0] == "compare_commits" for call in self.client.calls))

    def test_first_publication_needs_no_latest_comparison(self):
        del self.client.tags["latest"]
        del self.client.releases[1]
        self.client.main_values = [NEWER_SHA]
        self.assertFalse(self.publish().skipped)
        self.assertEqual(SHA, self.client.tags["latest"])
        self.assertEqual({("compare_commits", SHA, NEWER_SHA)},
                         {call for call in self.client.calls if call[0] == "compare_commits"})

    def test_latest_removed_from_main_history_is_replaced(self):
        self.client.main_values = [NEWER_SHA]
        self.client.tags["latest"] = REWRITTEN_SHA
        self.assertFalse(self.publish().skipped)
        self.assertEqual(SHA, self.client.tags["latest"])

    def test_diverged_build_is_skipped_while_latest_remains_on_main(self):
        # A merge put both commits on main; the build is not newer than Latest.
        self.client.main_values = [MERGE_SHA]
        self.client.tags["latest"] = SIDE_SHA
        self.assertTrue(self.publish().skipped)
        self.assertEqual([], self.client.writes)
        self.assertEqual(SIDE_SHA, self.client.tags["latest"])

    def test_history_change_at_each_guard_preserves_existing_latest(self):
        for guard in range(3):
            with self.subTest(guard=guard):
                self.client = FakeGitHub()
                self.client.main_values = [SHA] * guard + [FORCED_SHA]
                self.assertTrue(self.publish().skipped)
                self.assertIn(1, self.client.releases)
                self.assertEqual(OLDER_SHA, self.client.tags["latest"])
                self.assertNotIn(self.client.draft_id, self.client.releases)
                self.assertNotIn(("delete_release", 1), self.client.calls)
                self.assertFalse(any(call[0] == "promote_release" for call in self.client.calls))

    def test_invalid_main_or_compare_metadata_is_rejected(self):
        ancestor = {"status": "ahead", "merge_base_commit": {"sha": SHA}, "ahead_by": 1, "behind_by": 0}
        invalid = [None, [], {}, {"status": "behind"}, {"status": "diverged"}, {"status": "identical"}]
        for field, values in {"merge_base_commit": [None, {}, {"sha": OLDER_SHA}, {"sha": "main"}],
                              "behind_by": [None, True, 1, "0"]}.items():
            for value in values:
                invalid.append({**ancestor, field: value})
            invalid.append({key: entry for key, entry in ancestor.items() if key != field})
        for comparison in invalid:
            with self.subTest(comparison=comparison):
                self.client = FakeGitHub()
                self.client.main_values = [NEWER_SHA]
                self.client.comparisons[(SHA, NEWER_SHA)] = comparison
                self.assert_skipped_without_writes()
        for head in (None, "main", "g" * 40):
            with self.subTest(head=head):
                self.client = FakeGitHub()
                self.client.main_values = [head]
                self.assert_skipped_without_writes()

    def test_compare_request_failure_does_not_publish(self):
        self.client.main_values = [NEWER_SHA]
        with patch.object(self.client, "compare_commits", side_effect=publisher.APIError(403, "Forbidden")), \
                self.assertRaisesRegex(publisher.APIError, "HTTP 403"):
            self.publish()
        self.assertEqual([], self.client.writes)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])

    def test_upload_failure_keeps_existing_release(self):
        self.client.fail_upload = 2
        with self.assertRaisesRegex(publisher.APIError, "upload failed"):
            self.publish()
        self.assertIn(1, self.client.releases)
        self.assertLessEqual(self.client.staging_leftovers, set(self.client.releases))
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])
        self.assertFalse(any(call[0] in {"set_tag", "promote_release", "list_releases"}
                             for call in self.client.calls))
        self.assertNotIn(self.client.draft_id, self.client.releases)
        self.assertFalse(any(tag.startswith("build-123456-") for tag in self.client.tags))

    def test_digest_mismatch_keeps_existing_release(self):
        self.client.corrupt_digest = True
        with self.assertRaisesRegex(publisher.PublishError, "checksum does not match"):
            self.publish()
        self.assertIn(1, self.client.releases)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])
        self.assertFalse(any(call[0] == "promote_release" for call in self.client.calls))

    def test_stale_after_upload_cleans_only_its_draft(self):
        self.client.main_values = [SHA, OLDER_SHA]
        result = self.publish()
        self.assertTrue(result.skipped)
        self.assertEqual(5, self.client.upload_count)
        self.assertIn(1, self.client.releases)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])
        self.assertNotIn(self.client.draft_id, self.client.releases)
        self.assertNotIn(("delete_release", 1), self.client.calls)
        self.assertFalse(any(call[0] == "promote_release" for call in self.client.calls))

    def test_final_stale_check_keeps_existing_latest(self):
        self.client.main_values = [SHA, SHA, OLDER_SHA]
        result = self.publish()
        self.assertTrue(result.skipped)
        self.assertIn(1, self.client.releases)
        self.assertNotIn(self.client.draft_id, self.client.releases)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])

    def assert_previous_latest_restored(self):
        previous = self.client.releases[1]
        self.assertEqual("latest", previous["tag_name"])
        self.assertIs(False, previous["draft"])
        self.assertIn(("retag_release", 1, "latest", OLDER_SHA, True), self.client.calls)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])
        self.assertFalse(any(tag.startswith("latest-previous-123456-") for tag in self.client.tags))
        draft = self.client.releases[self.client.draft_id]
        self.assertTrue(draft["draft"])
        self.assertTrue(draft["tag_name"].startswith("build-123456-"))
        self.assertNotIn(("delete_release", 1), self.client.calls)

    def test_promotion_failure_restores_previous_latest_and_keeps_other_releases(self):
        self.client.fail_promotion = True
        with self.assertRaisesRegex(publisher.APIError, "promotion failed"):
            self.publish()
        self.assert_previous_latest_restored()
        self.assertLessEqual({4, 5, 6, 7, 8, 9}, set(self.client.releases))
        self.assertIn("v1.0.16", self.client.tags)
        self.assertFalse(any(call[0] == "list_releases" for call in self.client.calls))

    def test_tag_move_failure_restores_previous_latest(self):
        self.client.fail_tag_move = True
        with self.assertRaisesRegex(publisher.APIError, "tag move failed"):
            self.publish()
        self.assert_previous_latest_restored()
        self.assertFalse(any(call[0] == "promote_release" for call in self.client.calls))

    def test_incomplete_public_release_restores_previous_latest(self):
        self.client.corrupt_public = True
        with self.assertRaisesRegex(publisher.PublishError, "exactly the expected assets"):
            self.publish()
        self.assert_previous_latest_restored()
        self.assertLessEqual(self.client.staging_leftovers, set(self.client.releases))
        self.assertFalse(any(call[0] == "list_releases" for call in self.client.calls))

    def test_release_rename_failure_keeps_previous_latest(self):
        self.client.fail_retags = {1}
        with self.assertRaisesRegex(publisher.APIError, "release update failed"):
            self.publish()
        self.assert_previous_latest_restored()
        self.assertFalse(any(call[0] in {"set_tag", "promote_release"} and call[2] == SHA
                             for call in self.client.calls if len(call) > 2))

    def test_failed_restore_is_reported_and_keeps_previous_release_published(self):
        self.client.fail_promotion = True
        self.client.fail_retags = {2}
        stderr = io.StringIO()
        with patch.object(sys, "stderr", stderr), self.assertRaisesRegex(publisher.APIError, "promotion failed"):
            self.publish()
        self.assertIn("Could not restore the previous Latest release", stderr.getvalue())
        previous = self.client.releases[1]
        self.assertIs(False, previous["draft"])
        self.assertTrue(previous["tag_name"].startswith("latest-previous-123456-"))
        self.assertIn(previous["tag_name"], self.client.tags)

    def test_success_publishes_correct_sha_and_removes_only_interrupted_staging(self):
        result = self.publish()
        self.assertFalse(result.skipped)
        self.assertEqual(f"https://github.com/{REPOSITORY}/releases/tag/latest", result.url)
        self.assertEqual(5, result.assets)
        self.assertEqual(2, result.removed_staging)
        self.assertEqual(SHA, self.client.tags["latest"])
        release = self.client.releases[self.client.draft_id]
        self.assertFalse(release["draft"])
        self.assertFalse(release["prerelease"])
        self.assertEqual("Latest", release["name"])
        self.assertEqual(SHA, release["target_commitish"])
        self.assertEqual(set(publisher.ZIP_CONTENTS) | {publisher.CHECKSUM_NAME, publisher.UPDATE_MANIFEST_NAME},
                         {asset["name"] for asset in release["assets"]})
        self.assertEqual({4, 6, 7, 9, self.client.draft_id}, set(self.client.releases))
        self.assertEqual({"latest", "v1.0.16", "preview", "build-notes", "build-preserve-me"},
                         set(self.client.tags))
        calls = self.client.calls
        backup = next(call for call in calls if call[0] == "retag_release")
        self.assertEqual((1, OLDER_SHA, False), (backup[1], backup[3], backup[4]))
        self.assertTrue(backup[2].startswith("latest-previous-123456-"))
        uploaded = [index for index, call in enumerate(calls) if call[0] == "upload_asset"]
        self.assertLess(max(uploaded), calls.index(backup))
        self.assertLess(calls.index(backup), calls.index(("set_tag", "latest", SHA)))
        public_verify = [index for index, call in enumerate(calls)
                         if call == ("get_release", self.client.draft_id)][-1]
        old_release_delete = calls.index(("delete_release", 1))
        self.assertLess(public_verify, old_release_delete)
        self.assertLess(old_release_delete, calls.index(("delete_tag", backup[2])))
        for leftover in sorted(self.client.staging_leftovers):
            self.assertLess(public_verify, calls.index(("delete_release", leftover)))
        self.assertIn(("delete_tag", "latest-previous-77-0123456789ab"), calls)

    def test_previous_release_left_under_backup_tag_is_replaced(self):
        # A cancelled run moved the previous release aside and stopped before
        # promotion, so no release currently uses the latest tag.
        del self.client.releases[1]
        result = self.publish()
        self.assertFalse(result.skipped)
        self.assertEqual("latest", self.client.releases[self.client.draft_id]["tag_name"])
        self.assertNotIn(8, self.client.releases)
        self.assertNotIn("latest-previous-77-0123456789ab", self.client.tags)
        self.assertFalse(any(call[0] == "retag_release" for call in self.client.calls))

    def test_success_without_existing_latest(self):
        del self.client.releases[1]
        del self.client.tags["latest"]
        result = self.publish()
        self.assertFalse(result.skipped)
        self.assertEqual(SHA, self.client.tags["latest"])

    def test_github_without_asset_digests_still_checks_sizes_and_names(self):
        self.client.omit_digest = True
        self.assertFalse(self.publish().skipped)

    def test_redundant_addon_archive_is_not_published(self):
        (self.directory / "EraTalents-latest.zip").write_bytes(b"ignored artifact")
        self.publish()
        self.assertNotIn(("upload_asset", "EraTalents-latest.zip"), self.client.calls)

    def test_checksum_file_covers_three_public_zips_and_update_manifest(self):
        self.publish()
        checksum_lines = (self.directory / publisher.CHECKSUM_NAME).read_text().splitlines()
        self.assertEqual(4, len(checksum_lines))
        self.assertEqual(sorted(set(publisher.ZIP_CONTENTS) | {publisher.UPDATE_MANIFEST_NAME}),
                         [line.split("  ")[1] for line in checksum_lines])
        for line in checksum_lines:
            expected_digest, name = line.split("  ")
            payload = next(self.directory.rglob(name)).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_digest)

    def test_update_manifest_hashes_exact_final_archive_and_every_managed_file(self):
        self.publish()
        manifest = json.loads((self.directory / publisher.UPDATE_MANIFEST_NAME).read_text())
        path = next(self.directory.rglob(publisher.SERVER_PACKAGE_NAME))
        self.assertEqual(1, manifest["schema"])
        self.assertEqual(SHA, manifest["revision"])
        self.assertEqual(publisher.SERVER_PACKAGE_NAME, manifest["package"])
        self.assertEqual(path.stat().st_size, manifest["size"])
        self.assertEqual(publisher.digest(path), manifest["sha256"])
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(sorted(archive.namelist()), [entry["path"] for entry in manifest["files"]])
            for entry in manifest["files"]:
                content = archive.read(entry["path"])
                self.assertEqual(len(content), entry["size"])
                self.assertEqual(hashlib.sha256(content).hexdigest(), entry["sha256"])
        self.assertNotIn(publisher.UPDATE_MANIFEST_NAME, {entry["path"] for entry in manifest["files"]})

    def test_manifest_paths_accept_cmake_prefix_and_are_normalized(self):
        self.rewrite_server(prefix="./")
        self.publish()
        manifest = json.loads((self.directory / publisher.UPDATE_MANIFEST_NAME).read_text())
        self.assertTrue(all(not entry["path"].startswith("./") for entry in manifest["files"]))

    def test_manifest_rejects_mutable_user_data_before_api_calls(self):
        for name in UNMANAGED_PATHS["userData"]:
            with self.subTest(name=name):
                self.setUp()
                self.rewrite_server(extra={name: "private user data"})
                with self.assertRaisesRegex(publisher.PublishError, "Unmanaged user"):
                    self.publish()
                self.assertEqual([], self.client.calls)
                self.assertFalse((self.directory / publisher.UPDATE_MANIFEST_NAME).exists())

    def test_manifest_keeps_ordinary_package_files_beside_user_data_names(self):
        path = next(self.directory.rglob(publisher.SERVER_PACKAGE_NAME))
        with zipfile.ZipFile(path) as archive:
            present = set(archive.namelist())
        packaged = [name for name in UNMANAGED_PATHS["packaged"] if name not in present]
        self.rewrite_server(extra={name: f"package file: {name}" for name in packaged})
        self.assertFalse(self.publish().skipped)
        manifest = json.loads((self.directory / publisher.UPDATE_MANIFEST_NAME).read_text())
        self.assertLessEqual(set(packaged), {entry["path"] for entry in manifest["files"]})

    def test_manifest_rejects_duplicate_client_and_development_exports(self):
        for name in ("addons/MultiBot/Core.lua", "defaults/worldserver.conf", "CONTRIBUTING.md", "docs/building.md",
                     "src/data/sql/old/db_world/historical.sql", publisher.UPDATE_MANIFEST_NAME):
            with self.subTest(name=name):
                self.setUp()
                self.rewrite_server(extra={name: "redundant file"})
                with self.assertRaisesRegex(publisher.PublishError, "Unmanaged user or redundant"):
                    self.publish()
                self.assertEqual([], self.client.calls)

    def test_manifest_rejects_wrong_source_identity(self):
        identity = {"schema": 1, "revision": OLDER_SHA, "package": publisher.SERVER_PACKAGE_NAME, "version": "latest"}
        self.rewrite_server(replacements={"portable-release.json": json.dumps(identity)})
        with self.assertRaisesRegex(publisher.PublishError, "mismatched portable release identity"):
            self.publish()
        self.assertEqual([], self.client.calls)

    def test_manifest_rejects_unused_optional_tools_and_their_configuration(self):
        for name in ("dbimport.exe", "map_extractor.exe", "vmap4_extractor.exe", "vmap4_assembler.exe",
                     "mmaps_generator.exe", "mmaps-config.yaml", "configs/dbimport.conf.dist", "dbimport.conf.dist"):
            with self.subTest(name=name):
                self.setUp()
                self.rewrite_server(extra={name: "unused optional tool"})
                with self.assertRaisesRegex(publisher.PublishError, "Unmanaged user or redundant"):
                    self.publish()
                self.assertEqual([], self.client.calls)

    def test_manifest_rejects_invalid_identity_fields(self):
        for changes in ({"schema": 2}, {"revision": "main"}, {"package": "other.zip"}, {"version": "dev"}):
            with self.subTest(changes=changes):
                self.setUp()
                identity = {"schema": 1, "revision": SHA, "package": publisher.SERVER_PACKAGE_NAME, "version": "latest"}
                identity.update(changes)
                self.rewrite_server(replacements={"portable-release.json": json.dumps(identity)})
                with self.assertRaisesRegex(publisher.PublishError, "portable release identity"):
                    self.publish()
                self.assertEqual([], self.client.calls)

    def test_manifest_rejects_corrupted_file_even_if_required_headers_exist(self):
        path = next(self.directory.rglob(publisher.SERVER_PACKAGE_NAME))
        content = path.read_bytes()
        self.assertIn(b"test payload: startup.exe", content)
        path.write_bytes(content.replace(b"test payload: startup.exe", b"evil payload: startup.exe", 1))
        with self.assertRaisesRegex(publisher.PublishError, "file integrity verification"):
            self.publish()
        self.assertEqual([], self.client.calls)

    def test_manifest_rejects_unsafe_or_duplicate_windows_paths(self):
        for name in ("../user.db", "C:/private.db", "README.md:stream", "docs/CON.txt", "././bad.txt",
                     "WORLDserver.exe", "docs/../private.txt"):
            with self.subTest(name=name):
                self.setUp()
                self.rewrite_server(extra={name: "unsafe payload"})
                with self.assertRaisesRegex(publisher.PublishError, "Unsafe path|Duplicate path"):
                    self.publish()
                self.assertEqual([], self.client.calls)

    def test_manifest_rejects_file_directory_collision(self):
        self.rewrite_server(extra={"docs": "shadows docs directory"})
        with self.assertRaisesRegex(publisher.PublishError, "File/directory collision"):
            self.publish()
        self.assertEqual([], self.client.calls)

    def test_empty_notes_fail_before_api_writes(self):
        self.notes.write_text("\n  \n")
        with self.assertRaisesRegex(publisher.PublishError, "must not be empty"):
            self.publish()
        self.assertEqual([], self.client.writes)

    def test_unknown_template_field_fails_before_api_writes(self):
        self.notes.write_text("{unexpected}")
        with self.assertRaisesRegex(publisher.PublishError, "Unsupported release template field"):
            self.publish()
        self.assertEqual([], self.client.writes)

    def test_notes_pin_source_and_commit_to_the_built_revision(self):
        self.publish()
        body = self.client.releases[self.client.draft_id]["body"]
        self.assertIn(f"https://github.com/{REPOSITORY}/blob/{SHA}", body)
        self.assertIn(f"https://github.com/{REPOSITORY}/commit/{SHA}", body)
        self.assertIn(SHA[:12], body)

    def test_release_template_links_existing_documents_and_published_assets(self):
        root = Path(__file__).resolve().parents[2]
        template = root / ".github" / "RELEASE_TEMPLATE.md"
        notes = publisher.render_notes(template, REPOSITORY, SHA)
        source_url = f"https://github.com/{REPOSITORY}/blob/{SHA}/"
        documents = re.findall(re.escape(source_url) + r"([^)#\s]+)", notes)
        self.assertTrue(documents)
        for document in documents:
            with self.subTest(document=document):
                self.assertTrue((root / document).is_file())
        downloads = re.findall(rf"https://github[.]com/{re.escape(REPOSITORY)}/releases/latest/download/([^)\s]+)", notes)
        published = set(publisher.ZIP_CONTENTS) | {publisher.CHECKSUM_NAME, publisher.UPDATE_MANIFEST_NAME}
        self.assertTrue(downloads)
        self.assertLessEqual(set(downloads), published)
        self.assertLessEqual(set(publisher.ZIP_CONTENTS), set(downloads))

    def test_invalid_source_sha_or_run_id_makes_no_api_calls(self):
        for sha, run_id in [("main", "123"), (SHA, "not-a-run"), (SHA, "../../123")]:
            with self.subTest(sha=sha, run_id=run_id), self.assertRaises(publisher.PublishError):
                publisher.publish(self.client, sha, self.directory, self.notes, run_id)
        self.assertEqual([], self.client.calls)


class ClientTests(unittest.TestCase):
    def test_compare_uses_immutable_commit_range_without_pagination(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "_request", return_value={"status": "ahead"}) as request:
            result = client.compare_commits(SHA, NEWER_SHA)
        request.assert_called_once_with("GET", f"/compare/{SHA}...{NEWER_SHA}")
        self.assertEqual("ahead", result["status"])

    def test_missing_draft_tag_is_not_deleted(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        # Creating a draft does not create its ref. GitHub GET returns 404,
        # whereas DELETE would return 422 Reference does not exist.
        with patch.object(client, "_request", side_effect=publisher.APIError(404, "Not Found")) as request:
            client.delete_tag("build-123456-staging")
        request.assert_called_once_with("GET", "/git/ref/tags/build-123456-staging")

    def test_existing_tag_is_deleted(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", return_value=OLDER_SHA), patch.object(client, "_request") as request:
            client.delete_tag("latest-previous-1-0123456789ab")
        request.assert_called_once_with("DELETE", "/git/refs/tags/latest-previous-1-0123456789ab")

    def test_tag_removed_during_cleanup_accepts_422_only_after_confirming_absence(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", side_effect=[OLDER_SHA, None]) as lookup, patch.object(
                client, "_request", side_effect=publisher.APIError(422, "Reference does not exist")):
            client.delete_tag("build-123456-staging")
        self.assertEqual(2, lookup.call_count)

    def test_tag_delete_validation_failure_is_not_hidden(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", return_value=OLDER_SHA), patch.object(
                client, "_request", side_effect=publisher.APIError(422, "Protected ref")), \
                self.assertRaisesRegex(publisher.APIError, "Protected ref"):
            client.delete_tag("v1.0.16")

    def test_pagination_fetches_every_release(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path))
            if path.endswith("page=1"):
                return [{"id": number} for number in range(100)]
            return [{"id": 100}]

        with patch.object(client, "_request", side_effect=request):
            self.assertEqual(101, len(client.list_releases()))
        self.assertEqual([("GET", "/releases?per_page=100&page=1"), ("GET", "/releases?per_page=100&page=2")],
                         calls)

    def test_tag_update_is_forced_and_tag_creation_uses_full_ref(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", return_value=OLDER_SHA), patch.object(client, "_request") as request:
            client.set_tag("latest", SHA)
            request.assert_called_once_with("PATCH", "/git/refs/tags/latest", {"sha": SHA, "force": True})
        with patch.object(client, "tag_sha", return_value=None), patch.object(client, "_request") as request:
            client.set_tag("latest", SHA)
            request.assert_called_once_with("POST", "/git/refs", {"ref": "refs/tags/latest", "sha": SHA})

    def test_promotion_uses_the_latest_flag_and_public_stable_settings(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "_request") as request:
            client.promote_release(123, SHA, "notes")
        request.assert_called_once_with("PATCH", "/releases/123", {
            "tag_name": "latest", "target_commitish": SHA, "name": "Latest",
            "body": "notes", "draft": False, "prerelease": False, "make_latest": "true",
        })

    def test_release_swap_updates_use_tag_names_and_latest_flag(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "_request") as request:
            client.retag_release(1, "latest-previous-123-abc", OLDER_SHA)
            client.retag_release(1, "latest", OLDER_SHA, make_latest=True)
            client.retag_release(1, "latest", None, make_latest=True)
            client.return_to_draft(100, "build-123-abc")
        self.assertEqual([
            ("PATCH", "/releases/1", {"tag_name": "latest-previous-123-abc", "target_commitish": OLDER_SHA}),
            ("PATCH", "/releases/1", {"tag_name": "latest", "target_commitish": OLDER_SHA, "make_latest": "true"}),
            ("PATCH", "/releases/1", {"tag_name": "latest", "make_latest": "true"}),
            ("PATCH", "/releases/100", {"tag_name": "build-123-abc", "draft": True}),
        ], [call.args for call in request.call_args_list])

    def transient_failures(self, *failures):
        responses = list(failures)

        def open_request(request, timeout):
            self.opened.append(request.get_method())
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(json.dumps(response).encode())

        self.opened = []
        return patch.object(publisher, "urlopen", side_effect=open_request)

    @staticmethod
    def http_error(status):
        return HTTPError("https://api.github.com/", status, "error", None, io.BytesIO(b'{"message": "failed"}'))

    def test_idempotent_requests_repeat_transient_failures(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        for method in ("GET", "PATCH"):
            with self.subTest(method=method), patch.object(publisher.time, "sleep") as sleep, \
                    self.transient_failures(self.http_error(502), URLError("reset"), {"id": 1}):
                self.assertEqual({"id": 1}, client._request(method, "/releases/1", {} if method == "PATCH" else None))
                self.assertEqual([method] * 3, self.opened)
                self.assertEqual([((2,),), ((5,),)], sleep.call_args_list)

    def test_retries_stop_after_three_attempts(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(publisher.time, "sleep"), \
                self.transient_failures(self.http_error(503), self.http_error(502), self.http_error(500)), \
                self.assertRaisesRegex(publisher.APIError, "HTTP 500"):
            client._request("GET", "/releases/1")
        self.assertEqual(3, len(self.opened))

    def test_client_errors_and_non_idempotent_requests_are_not_repeated(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        for method, failure in (("GET", self.http_error(404)), ("PATCH", self.http_error(422)),
                                ("POST", self.http_error(502)), ("DELETE", URLError("reset"))):
            with self.subTest(method=method), patch.object(publisher.time, "sleep") as sleep, \
                    self.transient_failures(failure, {"id": 1}):
                with self.assertRaises(publisher.PublishError):
                    client._request(method, "/releases/1")
                self.assertEqual([method], self.opened)
                sleep.assert_not_called()

    def test_upload_streams_the_file_and_checks_github_upload_host(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "package.zip"
            path.write_bytes(b"test archive")
            asset = publisher.Asset(path, path.name, path.stat().st_size, publisher.digest(path))
            received = []

            def open_request(request, timeout):
                self.assertEqual(600, timeout)
                self.assertEqual("POST", request.method)
                self.assertEqual(str(asset.size), request.get_header("Content-length"))
                received.append(request.data.read())
                return io.BytesIO(json.dumps({"name": asset.name}).encode())

            with patch.object(publisher, "urlopen", side_effect=open_request):
                result = client.upload_asset({"upload_url": "https://uploads.github.com/repos/owner/repo/releases/1/assets{?name,label}"}, asset)
            self.assertEqual([b"test archive"], received)
            self.assertEqual(asset.name, result["name"])
            with self.assertRaisesRegex(publisher.PublishError, "unexpected asset upload URL"):
                client.upload_asset({"upload_url": "https://untrusted.invalid/upload"}, asset)

    def test_interrupted_publication_matches_only_publisher_staging_names(self):
        for tag, draft in (("build-123-0123456789ab", True), ("latest-previous-123-0123456789ab", False),
                           ("latest-previous-123-0123456789ab", True)):
            with self.subTest(tag=tag, draft=draft):
                self.assertTrue(publisher.is_interrupted_publication(
                    {"tag_name": tag, "name": "Latest", "draft": draft}))
        for release in ({"tag_name": "build-123-0123456789ab", "name": "Latest", "draft": False},
                        {"tag_name": "build-123-0123456789ab", "name": "Notes", "draft": True},
                        {"tag_name": "build-123", "name": "Latest", "draft": True},
                        {"tag_name": "build-123-0123456789AB", "name": "Latest", "draft": True},
                        {"tag_name": "latest", "name": "Latest", "draft": False},
                        {"tag_name": "v1.0.16", "name": "Latest", "draft": True},
                        {"tag_name": None, "name": "Latest", "draft": True}):
            with self.subTest(release=release):
                self.assertFalse(publisher.is_interrupted_publication(release))


if __name__ == "__main__":
    unittest.main()
