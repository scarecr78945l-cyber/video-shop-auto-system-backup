"""临时探测脚本（交付前删除）：确认嵌套 BaseSettings 环境变量映射机制。"""
import os
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TikTokConfigA(BaseSettings):
    # 方案 A：字段名 + env_prefix -> MATERIALS_BINARY_PATH
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")
    binary_path: str | None = None


class TikTokConfigB(BaseSettings):
    # 方案 B：validation_alias，去掉前缀（env=TIKTOK_BINARY）
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")
    binary_path: str | None = Field(default=None, validation_alias="TIKTOK_BINARY")


class TikTokConfigC(BaseSettings):
    # 方案 C：validation_alias，带前缀（env=MATERIALS_TIKTOK_BINARY）
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")
    binary_path: str | None = Field(default=None, validation_alias="MATERIALS_TIKTOK_BINARY")


class TikTokConfigD(BaseSettings):
    # 方案 D：别名同字段名（env=MATERIALS_BINARY_PATH 不设），验证 alias 是覆盖还是追加前缀
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")
    binary_path: str | None = Field(default=None, alias="TIKTOK_BINARY")


class TikTokConfigE(BaseSettings):
    # 方案 E：字段名 tiktok_binary（env=MATERIALS_TIKTOK_BINARY），再 property 暴露 binary_path
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")
    tiktok_binary: str | None = None

    @property
    def binary_path(self):
        return self.tiktok_binary


class TikTokConfigF(BaseSettings):
    # 方案 F：validation_alias 用 AliasChoices
    model_config = SettingsConfigDict(env_prefix="MATERIALS_", extra="ignore")
    binary_path: str | None = Field(default=None, validation_alias=AliasChoices("TIKTOK_BINARY"))


def show(tag, cfg):
    print(f"{tag}: binary_path={cfg.binary_path!r} (tiktok_binary={getattr(cfg, 'tiktok_binary', None)!r})")


os.environ.pop("MATERIALS_BINARY_PATH", None)
os.environ.pop("MATERIALS_TIKTOK_BINARY", None)
os.environ.pop("TIKTOK_BINARY", None)

print("== 无环境变量基线 ==")
show("A", TikTokConfigA())
show("B", TikTokConfigB())
show("C", TikTokConfigC())
show("D", TikTokConfigD())
show("E", TikTokConfigE())
show("F", TikTokConfigF())

print("== 设 MATERIALS_BINARY_PATH = x1 ==")
os.environ["MATERIALS_BINARY_PATH"] = "x1"
show("A", TikTokConfigA())

print("== 设 TIKTOK_BINARY = x2 ==")
os.environ["TIKTOK_BINARY"] = "x2"
show("B", TikTokConfigB())
show("D", TikTokConfigD())

print("== 设 MATERIALS_TIKTOK_BINARY = x3 ==")
os.environ["MATERIALS_TIKTOK_BINARY"] = "x3"
show("B", TikTokConfigB())
show("C", TikTokConfigC())
show("D", TikTokConfigD())
show("E", TikTokConfigE())
show("F", TikTokConfigF())
print("PROBE DONE")
