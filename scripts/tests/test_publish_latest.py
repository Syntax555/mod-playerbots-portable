"""Publication lifecycle tests; no network access or GitHub credentials required."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publish_latest as publisher


SHA = "a" * 40
OLDER_SHA = "b" * 40
NEWER_SHA = "c" * 40
REPOSITORY = "owner/mod-playerbots-portable"


def documentation_comparison(*paths):
    return {
        "status": "ahead", "base_commit": {"sha": SHA}, "merge_base_commit": {"sha": SHA},
        "ahead_by": 1, "behind_by": 0, "total_commits": 1,
        "files": [{"filename": path, "status": "modified"} for path in paths],
    }


class FakeGitHub:
    repository = REPOSITORY

    def __init__(self):
        self.calls = []
        self.main_values = [SHA]
        self.comparisons = {}
        self.fail_upload = None
        self.fail_promotion = False
        self.corrupt_digest = False
        self.omit_digest = False
        self.corrupt_public = False
        self.releases = {
            1: {"id": 1, "tag_name": "latest", "name": "Latest", "draft": False},
            2: {"id": 2, "tag_name": "v1.0.15"},
            3: {"id": 3, "tag_name": "v1.0.16"},
            4: {"id": 4, "tag_name": "preview"},
        }
        self.tags = {
            "latest": OLDER_SHA, "v1.0.15": OLDER_SHA, "v1.0.16": OLDER_SHA,
            "v0.9.0": OLDER_SHA, "preview": OLDER_SHA,
            "build-preserve-me": OLDER_SHA, "version-documentation": OLDER_SHA,
        }
        self.draft_id = 100
        self.upload_count = 0

    @property
    def writes(self):
        return [call for call in self.calls if call[0] in {
            "create_draft", "upload_asset", "delete_release", "set_tag", "delete_tag", "promote_release",
        }]

    def main_sha(self):
        self.calls.append(("main_sha",))
        if len(self.main_values) > 1:
            return self.main_values.pop(0)
        return self.main_values[0]

    def compare_commits(self, base, head):
        self.calls.append(("compare_commits", base, head))
        return copy.deepcopy(self.comparisons.get(head, {"status": "behind"}))

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
        self.releases[release_id].update({
            "tag_name": "latest", "target_commitish": sha, "name": "Latest",
            "body": notes, "draft": False, "prerelease": False,
            "html_url": f"https://github.com/{REPOSITORY}/releases/tag/latest",
        })

    def list_releases(self):
        self.calls.append(("list_releases",))
        return copy.deepcopy(list(self.releases.values()))

    def list_tags(self):
        self.calls.append(("list_tags",))
        return [{"name": tag} for tag in self.tags]


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

    def test_stale_build_makes_no_api_writes(self):
        self.client.main_values = [OLDER_SHA]
        result = self.publish()
        self.assertTrue(result.skipped)
        self.assertEqual([], self.client.writes)

    def test_current_commit_needs_no_compare_request(self):
        self.assertFalse(self.publish().skipped)
        self.assertFalse(any(call[0] == "compare_commits" for call in self.client.calls))

    def test_documentation_only_descendant_keeps_built_release_identity(self):
        self.client.main_values = [NEWER_SHA]
        self.client.comparisons[NEWER_SHA] = documentation_comparison(
            "README.md", "AGENTS.md", "CONTRIBUTING.md", "docs/era-talents.md", ".github/RELEASE_TEMPLATE.md",
        )
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

    def test_documentation_advancement_is_rechecked_at_all_three_guards(self):
        heads = [NEWER_SHA, "d" * 40, "e" * 40]
        self.client.main_values = heads.copy()
        for head in heads:
            self.client.comparisons[head] = documentation_comparison("docs/configuration.md")
        self.assertFalse(self.publish().skipped)
        self.assertEqual([("compare_commits", SHA, head) for head in heads],
                         [call for call in self.client.calls if call[0] == "compare_commits"])
        self.assertEqual(SHA, self.client.tags["latest"])

    def test_runtime_advancement_at_each_guard_preserves_existing_latest(self):
        for guard in range(3):
            with self.subTest(guard=guard):
                self.client = FakeGitHub()
                self.client.main_values = [SHA] * guard + [NEWER_SHA]
                self.client.comparisons[NEWER_SHA] = documentation_comparison("cmd/startup/main.go")
                self.assertTrue(self.publish().skipped)
                self.assertIn(1, self.client.releases)
                self.assertEqual(OLDER_SHA, self.client.tags["latest"])
                self.assertNotIn(self.client.draft_id, self.client.releases)
                self.assertNotIn(("delete_release", 1), self.client.calls)
                self.assertFalse(any(call[0] == "promote_release" for call in self.client.calls))

    def test_non_documentation_changes_make_no_api_writes(self):
        for name in ("cmd/startup/main.go", ".github/workflows/release.yml", "versions.lock.json",
                     "scripts/publish_latest.py", "THIRD_PARTY_NOTICES.md", "README.txt"):
            with self.subTest(name=name):
                self.client = FakeGitHub()
                self.client.main_values = [NEWER_SHA]
                self.client.comparisons[NEWER_SHA] = documentation_comparison(name)
                self.assertTrue(self.publish().skipped)
                self.assertEqual([], self.client.writes)

    def test_renaming_runtime_or_workflow_files_into_docs_is_rejected(self):
        for source in ("cmd/startup/main.go", ".github/workflows/release.yml", None):
            with self.subTest(source=source):
                self.client = FakeGitHub()
                self.client.main_values = [NEWER_SHA]
                comparison = documentation_comparison("docs/example.md")
                comparison["files"][0]["status"] = "renamed"
                if source is not None:
                    comparison["files"][0]["previous_filename"] = source
                self.client.comparisons[NEWER_SHA] = comparison
                self.assertTrue(self.publish().skipped)
                self.assertEqual([], self.client.writes)

    def test_documentation_rename_is_allowed(self):
        self.client.main_values = [NEWER_SHA]
        comparison = documentation_comparison("docs/new-guide.md")
        comparison["files"][0].update(status="renamed", previous_filename="docs/guide.md")
        self.client.comparisons[NEWER_SHA] = comparison
        self.assertFalse(self.publish().skipped)

    def test_compare_file_cap_is_rejected_but_smaller_complete_list_is_allowed(self):
        for count, skipped in ((299, False), (300, True)):
            with self.subTest(count=count):
                self.client = FakeGitHub()
                self.client.main_values = [NEWER_SHA]
                self.client.comparisons[NEWER_SHA] = documentation_comparison(
                    *(f"docs/guide-{index}.md" for index in range(count)),
                )
                self.assertEqual(skipped, self.publish().skipped)
                if skipped:
                    self.assertEqual([], self.client.writes)

    def test_ahead_commit_with_no_net_file_changes_is_allowed(self):
        self.client.main_values = [NEWER_SHA]
        self.client.comparisons[NEWER_SHA] = documentation_comparison()
        self.assertFalse(self.publish().skipped)

    def test_unknown_or_incomplete_compare_metadata_is_rejected(self):
        invalid = [None, [], {}, {"status": "behind"}, {"status": "diverged"}, {"status": "identical"}]
        fields = {
            "base_commit": [None, {}, {"sha": OLDER_SHA}],
            "merge_base_commit": [None, {}, {"sha": OLDER_SHA}],
            "ahead_by": [None, "1", True, 0], "behind_by": [None, True, 1],
            "total_commits": [None, True, 2], "files": [None, {}, [None], [{}]],
        }
        for field, values in fields.items():
            for value in values:
                comparison = documentation_comparison("README.md")
                comparison[field] = value
                invalid.append(comparison)
        for field in ("status", "base_commit", "merge_base_commit", "ahead_by", "behind_by", "total_commits", "files"):
            comparison = documentation_comparison("README.md")
            del comparison[field]
            invalid.append(comparison)
        for comparison in invalid:
            with self.subTest(comparison=comparison):
                self.client = FakeGitHub()
                self.client.main_values = [NEWER_SHA]
                self.client.comparisons[NEWER_SHA] = comparison
                self.assertTrue(self.publish().skipped)
                self.assertEqual([], self.client.writes)

    def test_unknown_file_status_or_invalid_documentation_paths_are_rejected(self):
        entries = [
            {"filename": "README.md"}, {"filename": "README.md", "status": "unknown"},
            {"filename": "README.md", "status": []}, {"filename": None, "status": "modified"},
            {"filename": "docs/../cmd/startup/main.go", "status": "modified"},
            {"filename": "docs/", "status": "modified"},
            {"filename": "docs/guide.md", "status": "modified", "previous_filename": "main.go"},
            {"filename": "docs/guide.md", "status": "copied"},
        ]
        for entry in entries:
            with self.subTest(entry=entry):
                self.client = FakeGitHub()
                self.client.main_values = [NEWER_SHA]
                comparison = documentation_comparison()
                comparison["files"] = [entry]
                self.client.comparisons[NEWER_SHA] = comparison
                self.assertTrue(self.publish().skipped)
                self.assertEqual([], self.client.writes)

    def test_compare_request_failure_does_not_publish(self):
        self.client.main_values = [NEWER_SHA]
        with patch.object(self.client, "compare_commits", side_effect=publisher.APIError(403, "Forbidden")):
            with self.assertRaisesRegex(publisher.APIError, "HTTP 403"):
                self.publish()
        self.assertEqual([], self.client.writes)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])

    def test_upload_failure_keeps_existing_release_and_versions(self):
        self.client.fail_upload = 2
        with self.assertRaisesRegex(publisher.APIError, "upload failed"):
            self.publish()
        self.assertIn(1, self.client.releases)
        self.assertIn(2, self.client.releases)
        self.assertIn(3, self.client.releases)
        self.assertEqual(OLDER_SHA, self.client.tags["latest"])
        self.assertFalse(any(call[0] in {"set_tag", "promote_release", "list_tags", "list_releases"}
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

    def test_promotion_failure_does_not_prune_version_history(self):
        self.client.fail_promotion = True
        with self.assertRaisesRegex(publisher.APIError, "promotion failed"):
            self.publish()
        self.assertIn(2, self.client.releases)
        self.assertIn(3, self.client.releases)
        self.assertIn("v0.9.0", self.client.tags)
        self.assertIn("v1.0.15", self.client.tags)
        self.assertIn("v1.0.16", self.client.tags)
        self.assertFalse(any(call[0] in {"list_releases", "list_tags"} for call in self.client.calls))
        self.assertIn(self.client.draft_id, self.client.releases)
        self.assertTrue(self.client.releases[self.client.draft_id]["draft"])

    def test_incomplete_public_release_does_not_prune_versions(self):
        self.client.corrupt_public = True
        with self.assertRaisesRegex(publisher.PublishError, "exactly the expected assets"):
            self.publish()
        self.assertIn(2, self.client.releases)
        self.assertIn(3, self.client.releases)
        self.assertFalse(any(call[0] in {"list_releases", "list_tags"} for call in self.client.calls))

    def test_success_publishes_correct_sha_and_prunes_only_numbered_tags(self):
        result = self.publish()
        self.assertFalse(result.skipped)
        self.assertEqual(f"https://github.com/{REPOSITORY}/releases/tag/latest", result.url)
        self.assertEqual(2, result.removed_releases)
        self.assertEqual(3, result.removed_tags)
        self.assertEqual(SHA, self.client.tags["latest"])
        release = self.client.releases[self.client.draft_id]
        self.assertFalse(release["draft"])
        self.assertFalse(release["prerelease"])
        self.assertEqual("Latest", release["name"])
        self.assertEqual(SHA, release["target_commitish"])
        self.assertEqual(set(publisher.ZIP_CONTENTS) | {publisher.CHECKSUM_NAME, publisher.UPDATE_MANIFEST_NAME},
                         {asset["name"] for asset in release["assets"]})
        self.assertEqual({4, self.client.draft_id}, set(self.client.releases))
        self.assertEqual({"latest", "preview", "build-preserve-me", "version-documentation"},
                         set(self.client.tags))
        calls = self.client.calls
        old_release_delete = calls.index(("delete_release", 1))
        uploaded = [index for index, call in enumerate(calls) if call[0] == "upload_asset"]
        self.assertLess(max(uploaded), old_release_delete)
        public_verify = [index for index, call in enumerate(calls)
                         if call == ("get_release", self.client.draft_id)][-1]
        self.assertLess(public_verify, calls.index(("delete_release", 2)))

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
        for name in ("configs/worldserver.conf", "mysql/data/user.db", "mysql/my.cnf", "mysql/my.ini",
                     "data/dbc/Spell.dbc", "logs/world.log", "configs/.portable-profiles.json", "configs/realm-phase.txt"):
            with self.subTest(name=name):
                self.setUp()
                self.rewrite_server(extra={name: "private user data"})
                with self.assertRaisesRegex(publisher.PublishError, "Unmanaged user"):
                    self.publish()
                self.assertEqual([], self.client.calls)
                self.assertFalse((self.directory / publisher.UPDATE_MANIFEST_NAME).exists())

    def test_manifest_rejects_duplicate_client_and_development_exports(self):
        for name in ("addons/MultiBot/Core.lua", "defaults/worldserver.conf", "CONTRIBUTING.md", "docs/building.md",
                     publisher.UPDATE_MANIFEST_NAME):
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

    def test_invalid_source_sha_or_run_id_makes_no_api_calls(self):
        for sha, run_id in [("main", "123"), (SHA, "not-a-run"), (SHA, "../../123")]:
            with self.subTest(sha=sha, run_id=run_id), self.assertRaises(publisher.PublishError):
                publisher.publish(self.client, sha, self.directory, self.notes, run_id)
        self.assertEqual([], self.client.calls)


class ClientTests(unittest.TestCase):
    def test_compare_uses_immutable_commit_range_without_pagination(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "_request", return_value=documentation_comparison("README.md")) as request:
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

    def test_existing_version_tag_is_deleted(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", return_value=OLDER_SHA), patch.object(client, "_request") as request:
            client.delete_tag("v1.0.16")
        request.assert_called_once_with("DELETE", "/git/refs/tags/v1.0.16")

    def test_tag_removed_during_cleanup_accepts_422_only_after_confirming_absence(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", side_effect=[OLDER_SHA, None]) as lookup, patch.object(
                client, "_request", side_effect=publisher.APIError(422, "Reference does not exist")):
            client.delete_tag("build-123456-staging")
        self.assertEqual(2, lookup.call_count)

    def test_tag_delete_validation_failure_is_not_hidden(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        with patch.object(client, "tag_sha", return_value=OLDER_SHA), patch.object(
                client, "_request", side_effect=publisher.APIError(422, "Protected ref")):
            with self.assertRaisesRegex(publisher.APIError, "Protected ref"):
                client.delete_tag("v1.0.16")

    def test_pagination_fetches_every_numbered_release_and_tag(self):
        client = publisher.GitHubClient(REPOSITORY, "test-token")
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path))
            if path.endswith("page=1"):
                return [{"name": f"v1.0.{number}"} for number in range(100)]
            return [{"name": "v1.0.100"}]

        with patch.object(client, "_request", side_effect=request):
            self.assertEqual(101, len(client.list_releases()))
            self.assertEqual(101, len(client.list_tags()))
        self.assertEqual([
            ("GET", "/releases?per_page=100&page=1"), ("GET", "/releases?per_page=100&page=2"),
            ("GET", "/tags?per_page=100&page=1"), ("GET", "/tags?per_page=100&page=2"),
        ], calls)

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

    def test_version_cleanup_regex_preserves_nonversion_tags(self):
        for tag in ("v1.0.16", "v2.1", "v2.1.3-rc.1", "v1.0.0+metadata"):
            with self.subTest(tag=tag):
                self.assertIsNotNone(publisher.VERSION_TAG.fullmatch(tag))
        for tag in ("latest", "main", "preview", "v1", "v1.0-guide", "release-v1.0.16", "build-123"):
            with self.subTest(tag=tag):
                self.assertIsNone(publisher.VERSION_TAG.fullmatch(tag))


if __name__ == "__main__":
    unittest.main()
