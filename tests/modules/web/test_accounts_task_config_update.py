from app.modules.web.routers.accounts import TaskConfigUpdate


def test_task_config_update_accepts_chinese_alias_keys():
    payload = {
        "寄养": {"enabled": True, "next_time": "2020-01-01 00:00"},
        "领取登录礼包": {"enabled": True, "next_time": "2020-01-01 00:00"},
        "领取邮件": {"enabled": True, "next_time": "2020-01-01 00:00"},
        "爬塔": {"enabled": True, "next_time": "2020-01-01 00:00"},
    }

    model = TaskConfigUpdate.model_validate(payload)
    dumped = model.model_dump(exclude_unset=True, by_alias=True)

    assert dumped["寄养"]["enabled"] is True
    assert dumped["领取登录礼包"]["enabled"] is True
    assert dumped["领取邮件"]["enabled"] is True
    assert dumped["爬塔"]["enabled"] is True


def test_task_config_update_empty_payload_stays_empty():
    model = TaskConfigUpdate.model_validate({})
    dumped = model.model_dump(exclude_unset=True, by_alias=True)
    assert dumped == {}
