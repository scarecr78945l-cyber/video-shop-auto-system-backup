"""临时探测脚本（交付前删除）：validation_alias + populate_by_name + 字典覆盖。"""
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TikTokConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore", populate_by_name=True)

    binary_path: str | None = Field(default=None, validation_alias="MATERIALS_TIKTOK_BINARY")
    timeout_seconds: int = Field(default=300, validation_alias="MATERIALS_TIKTOK_TIMEOUT_SECONDS")


class MaterialsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", env_file=".env", extra="ignore")

    tiktok: TikTokConfig = Field(default_factory=TikTokConfig)


os.environ["MATERIALS_TIKTOK_BINARY"] = "C:/tools/ttd.exe"
os.environ["MATERIALS_TIKTOK_TIMEOUT_SECONDS"] = "123"

c = MaterialsConfig()
assert c.tiktok.binary_path == "C:/tools/ttd.exe", c.tiktok.binary_path
assert c.tiktok.timeout_seconds == 123, c.tiktok.timeout_seconds
print("env OK:", c.tiktok.binary_path, c.tiktok.timeout_seconds)

c2 = MaterialsConfig(tiktok={"binary_path": "X", "timeout_seconds": 42})
assert c2.tiktok.binary_path == "X", c2.tiktok.binary_path
assert c2.tiktok.timeout_seconds == 42, c2.tiktok.timeout_seconds
print("dict-override-by-field-name OK:", c2.tiktok.binary_path, c2.tiktok.timeout_seconds)

c3 = MaterialsConfig(tiktok=TikTokConfig(binary_path="Y"))
assert c3.tiktok.binary_path == "Y", c3.tiktok.binary_path
print("model-override OK:", c3.tiktok.binary_path)
print("PROBE PASSED")
