from app.services.image_batcher import build_image_batches, estimate_page_count


def test_build_image_batches_returns_only_full_12_image_pages() -> None:
    image_paths = [f"image_{index}.png" for index in range(25)]

    batches = build_image_batches(image_paths)

    assert len(batches) == 2
    assert all(len(batch) == 12 for batch in batches)
    assert batches[0][0] == "image_0.png"
    assert batches[1][-1] == "image_23.png"


def test_estimate_page_count_uses_full_pages_only() -> None:
    assert estimate_page_count(0) == 0
    assert estimate_page_count(11) == 0
    assert estimate_page_count(12) == 1
    assert estimate_page_count(25) == 2
