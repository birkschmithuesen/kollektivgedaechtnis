from pathlib import Path

from PIL import Image

from kg.telegram_bot import TelegramSource


def make_source(tmp_path, chat_id=None, photos=None, texts=None):
    def downloader(file_id: str, dest: Path) -> None:
        Image.new("RGB", (800, 1000), (10, 120, 200)).save(dest)

    return TelegramSource(
        token="123:abc",
        chat_id=chat_id,
        photo_dir=tmp_path / "photos",
        portrait_dir=tmp_path / "portraits",
        portrait_size=64,
        on_photo=lambda photo, portrait, at: photos.append((photo, portrait, at)),
        on_text=lambda text, at: texts.append((text, at)),
        downloader=downloader,
    )


def photo_update(file_id="F1", date=1700.0, chat_id=42):
    return {
        "update_id": 1,
        "message": {
            "message_id": 7,
            "date": date,
            "chat": {"id": chat_id},
            "photo": [
                {"file_id": "small", "width": 90, "height": 120},
                {"file_id": file_id, "width": 800, "height": 1000},
            ],
        },
    }


def text_update(text="stop", date=1800.0, chat_id=42):
    return {
        "update_id": 2,
        "message": {"message_id": 8, "date": date, "chat": {"id": chat_id}, "text": text},
    }


async def test_photo_downloads_the_largest_size_and_normalises_it(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, photos=photos, texts=texts)

    await source.dispatch(photo_update())

    assert len(photos) == 1
    photo_path, portrait_path, at = photos[0]
    assert at == 1700.0
    assert photo_path.exists() and portrait_path.exists()
    with Image.open(portrait_path) as img:
        assert img.size == (64, 64)
        assert img.mode == "RGBA"
    assert texts == []


async def test_any_text_message_is_a_stop_signal(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, photos=photos, texts=texts)

    await source.dispatch(text_update(text="fertig", date=1900.0))

    assert texts == [("fertig", 1900.0)]
    assert photos == []


async def test_other_chats_are_ignored_when_a_chat_id_is_configured(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, chat_id=42, photos=photos, texts=texts)

    await source.dispatch(photo_update(chat_id=999))
    await source.dispatch(text_update(chat_id=999))

    assert photos == [] and texts == []


async def test_updates_without_a_message_are_ignored(tmp_path):
    photos, texts = [], []
    source = make_source(tmp_path, photos=photos, texts=texts)

    await source.dispatch({"update_id": 3})
    await source.dispatch({"update_id": 4, "message": {"date": 1.0, "chat": {"id": 42}}})

    assert photos == [] and texts == []


async def test_a_failed_download_does_not_raise(tmp_path):
    photos, texts = [], []

    def broken(file_id, dest):
        raise OSError("telegram offline")

    source = TelegramSource(
        token="123:abc",
        chat_id=None,
        photo_dir=tmp_path / "photos",
        portrait_dir=tmp_path / "portraits",
        portrait_size=64,
        on_photo=lambda photo, portrait, at: photos.append(photo),
        on_text=lambda text, at: texts.append(text),
        downloader=broken,
    )

    await source.dispatch(photo_update())

    assert photos == []
