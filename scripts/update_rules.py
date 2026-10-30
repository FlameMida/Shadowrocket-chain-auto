#!/usr/bin/env python3
"""把 Bettbox 原规则源转换为 Shadowrocket RULE-SET，并生成配置。"""
import argparse
import concurrent.futures
import ipaddress
import json
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UPSTREAM = "https://raw.githubusercontent.com/appshubcc/bett-rules/meta/geo/"
CLAUDE_URL = "https://raw.githubusercontent.com/Sor85/claude-ruleset/main/clash/claude.list"
DOMAIN_SOURCES = {
    "private": "private", "geolocation-cn": "geolocation-cn", "epicgames": "epicgames",
    "google": "google", "ai": "category-ai-!cn", "github": "github",
    "microsoft": "microsoft", "apple": "apple", "telegram": "telegram",
    "spotify": "spotify", "ads": "category-ads", "geolocation-!cn": "geolocation-!cn",
    "gfw": "gfw", "cn": "cn",
}
IP_SOURCES = {
    "private_ip": "private", "cn_ip": "cn", "google_ip": "google",
    "microsoft_ip": "microsoft", "apple_ip": "apple", "telegram_ip": "telegram",
    "spotify_ip": "spotify",
}

def rows(text):
    return [line.strip() for line in text.lstrip("﻿").splitlines()
            if line.strip() and not line.lstrip().startswith(("#", ";", "//"))]

def convert_domains(text):
    result = []
    for value in rows(text):
        suffix = value.startswith("+.")
        domain = value[2:] if suffix else value
        if not domain or any(c.isspace() for c in domain) or any(c in domain for c in ",/:*+|"):
            raise ValueError("不支持的域名条目：" + value)
        result.append(("DOMAIN-SUFFIX," if suffix else "DOMAIN,") + domain)
    if not result:
        raise ValueError("域名规则集为空")
    return list(dict.fromkeys(result))

def convert_ips(text):
    result = []
    for value in rows(text):
        network = ipaddress.ip_network(value, strict=True)
        kind = "IP-CIDR" if network.version == 4 else "IP-CIDR6"
        result.append(f"{kind},{network},no-resolve")
    if not result:
        raise ValueError("IP 规则集为空")
    return list(dict.fromkeys(result))

def convert_classical(text):
    result = []
    for value in rows(text):
        parts = [part.strip() for part in value.split(",")]
        if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != "no-resolve"):
            raise ValueError("不支持的 classical 条目：" + value)
        if parts[0] not in {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD", "IP-CIDR", "IP-CIDR6", "IP-ASN"}:
            raise ValueError("不支持的 classical 类型：" + value)
        if parts[0] in {"IP-CIDR", "IP-CIDR6"}:
            ipaddress.ip_network(parts[1], strict=True)
        result.append(",".join(parts))
    if not result:
        raise ValueError("classical 规则集为空")
    return list(dict.fromkeys(result))

def source_specs():
    specs = [(name, UPSTREAM + "geosite/" + source + ".list", convert_domains)
             for name, source in DOMAIN_SOURCES.items()]
    specs.extend((name, UPSTREAM + "geoip/" + source + ".list", convert_ips)
                 for name, source in IP_SOURCES.items())
    specs.append(("Anthropic", CLAUDE_URL, convert_classical))
    return specs

def fetch(spec):
    name, url, converter = spec
    request = urllib.request.Request(url, headers={"User-Agent": "Shadowrocket-Same-Source/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8-sig")
    return name, url, converter(text)

def inline_config(config, datasets):
    output = []
    for line in config.splitlines():
        if line.startswith("RULE-SET,"):
            _, url, target = line.split(",", 2)
            name = url.rsplit("/", 1)[-1].removesuffix(".list")
            for rule in datasets[name]:
                fields = rule.split(",")
                if fields[-1] == "no-resolve":
                    fields.insert(-1, target)
                else:
                    fields.append(target)
                output.append(",".join(fields))
        else:
            output.append(line)
    return "\n".join(output) + "\n"

def validate_config(config, datasets):
    section = ""
    sections = set()
    groups = {}
    rules = []
    for line in config.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith("["):
            if value in sections:
                raise ValueError("重复配置节：" + value)
            sections.add(value)
            section = value
        elif section == "[Proxy Group]":
            name, definition = value.split("=", 1)
            name = name.strip()
            if name in groups:
                raise ValueError("重复策略组：" + name)
            groups[name] = definition.strip()
        elif section == "[Rule]":
            rules.append(value)
    known = set(groups) | {"DIRECT", "REJECT", "PROXY", "TAILSCALE"}
    edges = {}
    for name, definition in groups.items():
        members = [v.strip() for v in definition.split(",")[1:] if "=" not in v]
        if any(member not in known for member in members):
            raise ValueError("未知组成员：" + name)
        edges[name] = [member for member in members if member in groups]
        default = re.search(r"policy-select-name=([^,]+)", definition)
        if default and default[1] not in members:
            raise ValueError("无效默认选项：" + name)
        regex = re.search(r"policy-regex-filter=(.*?)(?:, |$)", definition)
        if regex:
            re.compile(regex[1])
    def walk(name, path):
        if name in path:
            raise ValueError("策略组回环：" + " → ".join(path + [name]))
        for child in edges[name]:
            walk(child, path + [name])
    for name in groups:
        walk(name, [])
    for rule in rules:
        fields = rule.split(",")
        target = fields[-2] if fields[-1] == "no-resolve" else fields[-1]
        if target not in known:
            raise ValueError("未知规则目标：" + rule)
        if rule.startswith("RULE-SET,"):
            name = fields[1].rsplit("/", 1)[-1].removesuffix(".list")
            if name not in datasets:
                raise ValueError("未知规则集：" + name)
    if not rules or rules[-1] != "FINAL,默认代理":
        raise ValueError("缺少最终兜底规则")
    if "FCM" in groups or re.search(r"=\s*(url-test|load-balance|random|fallback)", config):
        raise ValueError("出现用户要求移除的分组")
    if groups.get("默认代理") != "select, PROXY, 链式落地, policy-select-name=PROXY":
        raise ValueError("默认代理没有跟随首页")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="待发布的 GitHub 所有者/仓库名")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("repository 格式应为所有者/仓库名")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.branch):
        parser.error("branch 不应包含路径或 URL 字符")
    template = (args.root / "Shadowrocket-chain-auto.conf.template").read_text()
    base = f"https://raw.githubusercontent.com/{args.repository}/{args.branch}/rules"
    config = template.replace("{{RULE_BASE}}", base)
    if "{{" in config:
        raise ValueError("存在未替换的模板参数")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, source_specs()))
    datasets = {name: data for name, _, data in fetched}
    validate_config(config, datasets)
    snapshot = inline_config(config, datasets)
    snapshot = snapshot.replace("规则自动更新版（发布后生效）", "同源静态快照版")
    snapshot = snapshot.replace("#!desc=原版同源规则，发布到托管仓库后开启 App 后台更新。", "#!desc=规则已内置，可离线导入；此快照不会自动更新。")
    snapshot = "# 此文件是静态快照，规则已内置；自动更新需使用发布后的 Shadowrocket-chain-auto.conf。\n" + snapshot
    validate_config(snapshot, datasets)
    if re.search(r"^(RULE-SET|DOMAIN-SET),", snapshot, re.M):
        raise ValueError("静态快照残留远程规则")
    manifest = {"sources": {name: {"url": url, "count": len(data)} for name, url, data in fetched}}
    # 所有下载和转换都成功后再写产物，失败不会把旧规则替换成空文件。
    args.root.mkdir(parents=True, exist_ok=True)
    rules_dir = args.root / "rules"
    rules_dir.mkdir(exist_ok=True)
    for name, url, data in fetched:
        content = "# 原始来源：" + url + "\n" + "\n".join(data) + "\n"
        with tempfile.NamedTemporaryFile(mode="w", dir=rules_dir, delete=False, encoding="utf-8") as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(rules_dir / (name + ".list"))
    (args.root / "Shadowrocket-chain-auto.conf").write_text(config)
    (args.root / "Shadowrocket-snapshot.conf").write_text(snapshot)
    (args.root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (args.root / "last-success.txt").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    print(f"转换成功：{len(datasets)} 个同源规则集，{sum(map(len, datasets.values()))} 条规则")
    print("托管配置：" + str(args.root / "Shadowrocket-chain-auto.conf"))
    print("静态快照：" + str(args.root / "Shadowrocket-snapshot.conf"))
    print("托管配置必须在规则文件发布后才能使用；生成成功不代表已发布。")

if __name__ == "__main__":
    main()
