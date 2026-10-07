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
REPOSITORY = "owner/mod-playerbots-portable"


class FakeGitHub:
    repository = REPOSITORY

    def __init__(self):
        self.calls = []
        self.main_values = [SHA]
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
                    archive.writestr(entry, f"test payload: {entry}")
        self.notes = self.directory / "notes.md"
        self.notes.write_text(
            "Download Latest from {repository_url}. Source: {source_url}. "
            "Build [{revision}]({commit_url}).\n", encoding="utf-8",
        )
        self.client = FakeGitHub()

    def publish(self):
        return publisher.publish(self.client, SHA, self.directory, self.notes, "123456")

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
        self.assertEqual(4, self.client.upload_count)
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
        self.assertEqual(set(publisher.ZIP_CONTENTS) | {publisher.CHECKSUM_NAME},
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

    def test_checksum_file_covers_exactly_the_three_public_zips(self):
        self.publish()
        checksum_lines = (self.directory / publisher.CHECKSUM_NAME).read_text().splitlines()
        self.assertEqual(3, len(checksum_lines))
        self.assertEqual(sorted(publisher.ZIP_CONTENTS), [line.split("  ")[1] for line in checksum_lines])
        for line in checksum_lines:
            expected_digest, name = line.split("  ")
            payload = next(self.directory.rglob(name)).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_digest)

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
