from app.ui.components.chart_theme import STYLE_CLEAN
from app.ui.pages.company import _SAMPLE_QUARTERS, _sample_chart


def test_sample_chart_uses_explicit_year_quarter_labels() -> None:
    assert _SAMPLE_QUARTERS[0] == "FY23 Q1"
    assert _SAMPLE_QUARTERS[-1] == "FY25 Q4"
    assert "Q12" not in _SAMPLE_QUARTERS

    fig = _sample_chart(STYLE_CLEAN)

    assert tuple(fig.data[0].x) == _SAMPLE_QUARTERS
    assert tuple(fig.data[1].x) == _SAMPLE_QUARTERS
