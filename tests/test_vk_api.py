"""Tests for vk_api.py."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
import requests

from vk_uploader.vk_api import VkApiError, VkClient


def make_json_response(json_data: dict, status_code: int = 200) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = __import__("json").dumps(json_data).encode()
    return resp


@pytest.fixture
def client():
    return VkClient(access_token="test-token")


def make_ok_response(response_data: dict | list) -> requests.Response:
    return make_json_response({"response": response_data})


def make_error_response(code: int, msg: str) -> requests.Response:
    return make_json_response({"error": {"error_code": code, "error_msg": msg}})


class TestCallMethod:
    def test_returns_response_on_success(self, mocker):
        mocker.patch("vk_uploader.vk_api.requests.post", return_value=make_ok_response({"ok": 1}))
        client = VkClient("tok")
        result = client.call_method("users.get", {})
        assert result == {"ok": 1}

    def test_raises_vk_api_error_on_error(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_error_response(5, "Invalid token"),
        )
        client = VkClient("tok")
        with pytest.raises(VkApiError) as exc:
            client.call_method("users.get", {})
        assert exc.value.code == 5
        assert "Invalid token" in exc.value.message

    def test_passes_token_and_version(self, mocker):
        mock = mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({}),
        )
        client = VkClient("my-token", api_version="5.100")
        client.call_method("users.get", {"extra": "val"})
        call_data = mock.call_args.kwargs["data"]
        assert call_data["access_token"] == "my-token"
        assert call_data["v"] == "5.100"
        assert call_data["extra"] == "val"


class TestUsersGet:
    def test_returns_user_list(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response([{"id": 1, "first_name": "Test"}]),
        )
        client = VkClient("tok")
        users = client.users_get()
        assert users == [{"id": 1, "first_name": "Test"}]


class TestVideoSave:
    def test_returns_vk_save_response(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "upload_url": "https://upload.vk.com/video",
                "video_id": 123,
                "owner_id": -456,
            }),
        )
        client = VkClient("tok")
        result = client.video_save(
            name="My video",
            description="Desc",
            group_id="999",
            publish_at=datetime.datetime(2026, 6, 1, 12, 0, 0),
        )
        assert result.upload_url == "https://upload.vk.com/video"
        assert result.video_id == 123
        assert result.owner_id == -456

    def test_includes_thumb_url_when_provided(self, mocker):
        mock = mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "upload_url": "https://upload.vk.com/video",
                "video_id": 1,
                "owner_id": 2,
            }),
        )
        client = VkClient("tok")
        client.video_save(
            name="x", description="x", group_id="1",
            publish_at=datetime.datetime.now(),
            thumb_url="https://i.ytimg.com/thumb.jpg",
        )
        call_data = mock.call_args.kwargs["data"]
        assert call_data["thumb_url"] == "https://i.ytimg.com/thumb.jpg"

    def test_formats_publish_date_as_unix(self, mocker):
        mock = mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "upload_url": "https://upload.vk.com/video",
                "video_id": 1,
                "owner_id": 2,
            }),
        )
        client = VkClient("tok")
        dt = datetime.datetime(2026, 6, 1, 12, 0, 0, tzinfo=datetime.UTC)
        client.video_save(name="x", description="x", group_id="1", publish_at=dt)
        call_data = mock.call_args.kwargs["data"]
        expected_ts = str(int(dt.timestamp()))
        assert call_data["publish_date"] == expected_ts

    def test_raises_when_upload_url_missing(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({"video_id": 1}),
        )
        client = VkClient("tok")
        with pytest.raises(VkApiError) as exc:
            client.video_save(
                name="x", description="x", group_id="1",
                publish_at=datetime.datetime.now(),
            )
        assert "upload_url" in exc.value.message.lower()


class TestUploadVideoFile:
    def test_returns_upload_result(self, mocker, tmp_path: Path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video data")

        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_json_response({"video_id": 10, "owner_id": 20}),
        )
        client = VkClient("tok")
        result = client.upload_video_file("https://upload.vk.com/v", video_file)
        assert result.video_id == 10
        assert result.owner_id == 20

    def test_raises_on_vk_error(self, mocker, tmp_path: Path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake")

        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_error_response(7, "Upload denied"),
        )
        client = VkClient("tok")
        with pytest.raises(VkApiError) as exc:
            client.upload_video_file("https://upload.vk.com/v", video_file)
        assert "Upload denied" in exc.value.message


class TestUploadVideoThumbnail:
    def test_upload_thumbnail_flow(self, mocker, tmp_path: Path):
        thumb = tmp_path / "thumb.jpg"
        thumb.write_bytes(b"fake jpg")

        # Mock call_method: first for getThumbUploadUrl, second for saveUploadedThumb.
        call_responses = [
            make_ok_response({"upload_url": "https://thumb-upload.vk.com/url"}),
            make_ok_response({"success": 1}),
        ]
        call_mock = mocker.patch.object(
            VkClient,
            "call_method",
            side_effect=lambda method, params: (
                call_responses.pop(0).json()["response"]
            ),
        )
        # Mock the image file upload.
        post_mock = mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_json_response({"photo": "uploaded"}),
        )

        client = VkClient("tok")
        result = client.upload_video_thumbnail(
            video_id=10, owner_id=-20, thumbnail_path=thumb,
        )

        assert result == {"success": 1}
        # Verify image was POSTed.
        assert post_mock.call_args.kwargs["files"] is not None
        # Verify getThumbUploadUrl was called.
        assert any(
            "video.getThumbUploadUrl" in str(c)
            for c in call_mock.call_args_list
        )


class TestGetAlbums:
    def test_returns_album_list(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "count": 2,
                "items": [
                    {"id": 10, "title": "Album A", "count": 5},
                    {"id": 11, "title": "Album B", "count": 3},
                ],
            }),
        )
        client = VkClient("tok")
        albums = client.get_albums("-12345")
        assert len(albums) == 2
        assert albums[0]["title"] == "Album A"

    def test_returns_empty_list_when_no_albums(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({"count": 0, "items": []}),
        )
        client = VkClient("tok")
        albums = client.get_albums("-12345")
        assert albums == []


class TestAddAlbum:
    def test_returns_album_id(self, mocker):
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({"album_id": 42}),
        )
        client = VkClient("tok")
        album_id = client.add_album("12345", "My Playlist")
        assert album_id == 42


class TestVideoSaveAlbum:
    def test_passes_album_id_when_set(self, mocker):
        mock = mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "upload_url": "https://up.vk.com/v",
                "video_id": 1,
                "owner_id": -1,
            }),
        )
        client = VkClient("tok")
        client.video_save(
            name="x", description="x", group_id="1",
            publish_at=datetime.datetime(2026, 6, 1, 12, 0, 0),
            album_id="42",
        )
        call_data = mock.call_args.kwargs["data"]
        assert call_data["album_id"] == "42"

    def test_omits_album_id_when_none(self, mocker):
        mock = mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "upload_url": "https://up.vk.com/v",
                "video_id": 1,
                "owner_id": -1,
            }),
        )
        client = VkClient("tok")
        client.video_save(
            name="x", description="x", group_id="1",
            publish_at=datetime.datetime(2026, 6, 1, 12, 0, 0),
            album_id=None,
        )
        call_data = mock.call_args.kwargs["data"]
        assert "album_id" not in call_data


class TestResolveAlbum:
    def test_noninteractive_finds_by_name(self, mocker):
        """When album_spec is a name, find existing album by name."""
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "count": 1,
                "items": [{"id": 55, "title": "My Playlist", "count": 3}],
            }),
        )
        from vk_uploader.vk_api import resolve_album

        console = mocker.MagicMock()
        album_id, status = resolve_album(
            VkClient("tok"), "12345", "My Playlist", console,
        )
        assert album_id == "55"

    def test_noninteractive_creates_when_not_found(self, mocker):
        """When album_spec name not found, create new album."""
        responses = iter([
            make_ok_response({"count": 0, "items": []}),
            make_ok_response({"album_id": 77}),
        ])
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            side_effect=lambda *a, **kw: next(responses),
        )
        from vk_uploader.vk_api import resolve_album

        console = mocker.MagicMock()
        album_id, status = resolve_album(
            VkClient("tok"), "12345", "New Album", console,
        )
        assert album_id == "77"

    def test_interactive_cancel_returns_none(self, mocker):
        """Interactive mode: user presses Enter with no input."""
        mocker.patch(
            "vk_uploader.vk_api.requests.post",
            return_value=make_ok_response({
                "count": 1,
                "items": [{"id": 10, "title": "Test", "count": 1}],
            }),
        )
        from vk_uploader.vk_api import resolve_album

        console = mocker.MagicMock()
        console.input.return_value = "invalid-choice"
        album_id, status = resolve_album(
            VkClient("tok"), "12345", "true", console,
        )
        assert album_id is None
