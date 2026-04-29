from __future__ import annotations

import json

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.proactive.types import FeishuSendResult


class FeishuConfigurationError(RuntimeError):
    pass


class FeishuDeliveryError(RuntimeError):
    def __init__(self, message: str, *, log_id: str | None = None) -> None:
        super().__init__(message)
        self.log_id = log_id


class FeishuMessageSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: lark.Client | None = None

    def send_text(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        text: str,
        uuid: str,
    ) -> FeishuSendResult:
        if not receive_id:
            raise FeishuConfigurationError("Feishu receive_id is required")
        client = self._get_client()
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(receive_id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .uuid(uuid)
                .build()
            )
            .build()
        )
        response = client.im.v1.message.create(request)
        if not response.success():
            message = response.msg or "Feishu message send failed"
            raise FeishuDeliveryError(message, log_id=response.get_log_id())

        return FeishuSendResult(
            message_id=response.data.message_id if response.data else "",
            chat_id=response.data.chat_id if response.data else None,
            create_time=response.data.create_time if response.data else None,
            log_id=response.get_log_id(),
        )

    def _get_client(self) -> lark.Client:
        if self._client is not None:
            return self._client
        if not self._settings.feishu_app_id or not self._settings.feishu_app_secret:
            raise FeishuConfigurationError(
                "LONGMEMORY_FEISHU_APP_ID and LONGMEMORY_FEISHU_APP_SECRET must be configured before sending reminders; confirm the Feishu app has im:message:send_as_bot permission"
            )
        domain = lark.FEISHU_DOMAIN if self._settings.feishu_domain == "feishu" else lark.LARK_DOMAIN
        self._client = (
            lark.Client.builder()
            .app_id(self._settings.feishu_app_id)
            .app_secret(self._settings.feishu_app_secret)
            .domain(domain)
            .build()
        )
        return self._client
