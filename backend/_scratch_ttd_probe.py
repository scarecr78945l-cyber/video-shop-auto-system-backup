"""临时探测脚本（交付前删除）：验证 pydantic-settings 嵌套 BaseSettings 环境变量映射。"""
import os
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TikTokConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")

    binary_path: str | None = Field(default=None, validation_alias="TIKTOK_BINARY")
    timeout_seconds: int = Field(default=300, validation_alias="TIKTOK_TIMEOUT_SECONDS")
    default_output_dir: str = Field(default="data/tiktok_downloads", validation_alias="TIKTOK_OUTPUT_DIR")
    version_pin: str = Field(default="", validation_alias="TIKTOK_VERSION_PIN")
    enabled: dict[str, bool] = Field(
        default_factory=lambda: {"douyin": True, "kuaishou": True, "xiaohongshu": True},
        validation_alias="TIKTOK_ENABLED",
    )


class MaterialsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", env_file=".env", extra="ignore")

    tiktok: TikTokConfig = Field(default_factory=TikTokConfig)


os.environ["MATERIALS_TIKTOK_BINARY"] = "C:/tools/ttd.exe"
os.environ["MATERIALS_TIKTOK_TIMEOUT_SECONDS"] = "123"
os.environ["MATERIALS_TIKTOK_OUTPUT_DIR"] = "C:/out"
c = MaterialsConfig()
assert c.tiktok.binary_path == "C:/tools/ttd.exe", c.tiktok.binary_path
assert c.tiktok.timeout_seconds == 123, c.tiktok.timeout_seconds
assert c.tiktok.default_output_dir == "C:/out", c.tiktok.default_output_dir
print("env-mapping OK:", c.tiktok.binary_path, c.tiktok.timeout_seconds, c.tiktok.default_output_dir)

c2 = MaterialsConfig(tiktok={"binary_path": "X", "timeout_seconds": 42, "enabled": {"douyin": False}})
assert c2.tiktok.binary_path == "X" and c2.tiktok.timeout_seconds == 42
assert c2.tiktok.enabled == {"douyin": False}, c2.tiktok.enabled
print("override OK:", c2.tiktok.binary_path, c2.tiktok.timeout_seconds, c2.tiktok.enabled)
print("PROBE PASSED")
