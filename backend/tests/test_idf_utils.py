from pathlib import Path

from app.energyplus.idf_utils import list_zone_names, parse_err_file, summarize_errors, validate_idf_references


def test_parse_err_file(tmp_path: Path) -> None:
    err = tmp_path / "eplusout.err"
    err.write_text(
        "Program Version,EnergyPlus, Version 24.1.0\n"
        "   ** Warning ** Weather file location will be used rather than entered location.\n"
        "   ** Severe  ** GetZoneData: Errors found in Zone.\n"
        "   **  Fatal  ** Errors found in getting input. Program terminates.\n"
    )
    events = parse_err_file(err)
    assert len(events) == 3
    assert events[0].severity == "warning"
    assert events[1].severity == "severe"
    assert events[2].severity == "fatal"


def test_parse_err_file_missing(tmp_path: Path) -> None:
    assert parse_err_file(tmp_path / "does_not_exist.err") == []


def test_summarize_errors_empty() -> None:
    assert "No warnings" in summarize_errors([])


def test_summarize_errors_prioritizes_fatal(tmp_path: Path) -> None:
    err = tmp_path / "eplusout.err"
    err.write_text(
        "   ** Warning ** minor issue one.\n"
        "   **  Fatal  ** everything is on fire.\n"
    )
    events = parse_err_file(err)
    summary = summarize_errors(events, max_items=1)
    assert "everything is on fire" in summary
    assert "minor issue" not in summary


def test_list_zone_names(tmp_path: Path) -> None:
    idf = tmp_path / "test.idf"
    idf.write_text(
        "Zone,\n  ZONE A,\n  0,0,0,0,1,1,,autocalculate;\n"
        "Zone,\n  ZONE B,\n  0,0,0,0,1,1,,autocalculate;\n"
    )
    assert list_zone_names(idf) == ["ZONE A", "ZONE B"]


def test_validate_idf_references_catches_dangling_zone(tmp_path: Path) -> None:
    idf = tmp_path / "broken.idf"
    idf.write_text(
        "Zone,ZONE A,0,0,0,0,1,1,,autocalculate;\n"
        "People,ZoneA People,ZONE B,Occupancy Schedule,People,8;\n"
    )
    errors = validate_idf_references(idf)
    assert any("unknown zone" in e for e in errors)


def test_validate_idf_references_catches_dangling_equipment_list() -> None:
    idf = str(Path(__file__).parent.parent / "models" / "small_office.idf")
    # Sanity: the real shipped model should have zero dangling references.
    errors = validate_idf_references(idf)
    assert errors == [], f"small_office.idf has dangling references:\n" + "\n".join(errors)


def test_validate_idf_references_missing_file() -> None:
    errors = validate_idf_references("/nonexistent/path.idf")
    assert len(errors) == 1
    assert "not found" in errors[0]
