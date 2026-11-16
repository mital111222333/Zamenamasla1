"""Соглашение заполнено полностью: нет пустых мест вида [_____] и данные исполнителя на месте."""
import re

import oferta


def test_no_blanks_left():
    text = open(oferta.OFERTA_PATH, encoding="utf-8").read()
    assert not re.search(r"\[[^\]]*\]", text), re.findall(r"\[[^\]]*\]", text)
    assert "___" not in text
    for must in ("Saidmuratov Saidbonur Jaxongir o'g'li", "STIR: 550110220", "Mirzo Ulug'bek",
                 "+998 99 777 70 11", "@Saidbonur405", "oilbook.uz/oferta"):
        assert must in text, must
