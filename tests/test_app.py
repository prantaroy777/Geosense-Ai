from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_demo_ui_runs():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    assert not app.exception
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 3


def test_prepared_mask_ui_runs():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    app.selectbox(key="analysis_choice").select("prepared_mask").run()
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert not app.error
    assert len(app.metric) == 3


def test_binary_upload_suggests_mask_without_metadata_error(monkeypatch):
    from io import BytesIO
    import streamlit as st
    from geosense.demo import demo_scenes, scene_bytes

    _, scene = demo_scenes()
    scene.bands = {"mask": scene.bands["mask"]}
    uploaded = BytesIO(scene_bytes(scene))
    uploaded.name = "binary_event.tif"
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    monkeypatch.setattr(
        st,
        "file_uploader",
        lambda *args, **kwargs: uploaded if kwargs.get("key") == "after" else None,
    )
    app.radio[0].set_value("Upload GeoTIFF").run(timeout=30)
    assert not app.exception
    assert not app.error
    assert any("existing event mask" in item.value for item in app.warning)
    app.button(key="after_switch").click().run(timeout=30)
    assert not app.error
    assert app.selectbox(key="analysis_choice").value == "prepared_mask"


def test_vector_upload_and_export(monkeypatch):
    import json
    from io import BytesIO
    import streamlit as st

    doc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Example"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[13, 52], [13.01, 52], [13.01, 52.01], [13, 52.01], [13, 52]]
                    ],
                },
            }
        ],
    }
    upload = BytesIO(json.dumps(doc).encode())
    upload.name = "observedEvent.geojson"
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    monkeypatch.setattr(
        st,
        "file_uploader",
        lambda *args, **kwargs: (
            [upload] if kwargs.get("key") == "vector_files" else None
        ),
    )
    app.radio[0].set_value("GIS vector package").run(timeout=30)
    assert not app.error
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert not app.error
    assert len(app.metric) == 1


def test_monitoring_demo_ui():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(
        timeout=30
    )
    app.radio[0].set_value("Monitoring & run library").run(timeout=30)
    assert not app.exception
    app.button[0].click().run(timeout=30)
    assert not app.error
    assert not app.exception
    assert len(app.metric) == 3
