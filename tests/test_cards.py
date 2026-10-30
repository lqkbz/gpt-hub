import pytest

from core.cards import CardError, card_to_role


def card(**data):
    base = {"name": "标题", "description": "", "personality": "", "scenario": "", "first_mes": "",
            "mes_example": "", "system_prompt": "", "post_history_instructions": "", "tags": []}
    base.update(data)
    return {"spec": "chara_card_v2", "data": base}


def test_basic_conversion():
    res = card_to_role(card(
        description="name: 伊莉莎白\nage: 18\n{{char}}喜欢{{user}}，和{{user}}是同班同学",
        personality="傲娇", scenario="放学后", first_mes="哼，{{user}}你来了",
        mes_example="<START>\n{{user}}: 你好\n{{char}}: 哼", tags=["NSFW", "Tsundere"],
    ), "伊莉莎白")
    r = res.role
    assert r.name == "伊莉莎白"
    assert "伊莉莎白喜欢用户" in r.prompt and "{{" not in r.prompt
    assert "age: 20" in r.prompt and "age: 18" not in r.prompt
    assert "【性格】\n傲娇" in r.prompt and "【场景】\n放学后" in r.prompt
    assert "成年" in r.prompt and "大学" in r.prompt
    assert r.greeting == "哼，你你来了" or r.greeting == "哼，你来了"
    assert "<START>" not in r.examples and "用户: 你好" in r.examples
    assert r.nsfw is True
    assert any("年龄" in n for n in res.notes)


def test_nsfw_detected_from_text():
    assert card_to_role(card(description="NSFW/Sexual Content allowed"), "x").role.nsfw is True
    assert card_to_role(card(description="普通角色"), "x").role.nsfw is False


def test_missing_age_noted():
    res = card_to_role(card(description="一个女孩"), "x")
    assert "成年" in res.role.prompt
    assert any("未写明年龄" in n for n in res.notes)


@pytest.mark.parametrize("desc", ["age: 16", "年龄：15岁", "Age: 12"])
def test_minor_rejected(desc):
    with pytest.raises(CardError):
        card_to_role(card(description=desc), "x")


def test_plain_v1_card_and_empty():
    res = card_to_role({"name": "n", "description": "age: 25\n御姐"}, "御姐")
    assert "age: 25" in res.role.prompt
    with pytest.raises(CardError):
        card_to_role(card(), "x")
