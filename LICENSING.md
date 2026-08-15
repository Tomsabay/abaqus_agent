# 授权说明 / Licensing

Abaqus Agent 采用 **AGPL-3.0-or-later + 商业授权** 的双许可模式。
本页把价格和联系方式直接写出来，不搞"联系我们获取报价"。

**联系方式**：zhaoshaofeng892@gmail.com（主题请写 `[授权]`）

---

## 先说一件事：多数人不需要买

AGPL 常被过度解读成"碰了就得开源"。它不是。按 AGPL 使用本项目是**完全免费**的，
包括商业环境。以下情形你**不需要**任何付费授权：

- 在你公司内部用它跑仿真、出报告、交付给你的客户 —— 报告和结果是你的，
  AGPL 管的是软件本身，不是软件算出来的东西
- 修改它、自己内部部署，只要愿意把源码给**用它的那些人**（内部部署时，
  这通常意味着给同事一个内网 Git 地址就满足了）
- 研究、教学、写论文、录教程
- fork 出去继续以 AGPL 开发

只有下面两种情况才需要商业授权。如果你不属于这两类，请不要花这个钱。

---

## 什么情况需要商业授权

**情形 A —— 闭源分发**
你要把本项目（或其修改版、或包含它的产品）交付到你公司之外，同时**不愿意**
向接收方提供完整对应源码。典型场景：把它嵌进你自己卖的软件、打包进设备、
作为交付物给甲方而不带源码。

**情形 B —— 对外提供网络服务**
你要把它做成别人通过网络使用的服务（SaaS、内部平台对外开放、API），
同时**不愿意**向这些使用者提供完整对应源码。这是 AGPL 第 13 条的适用场景，
也是它和 GPL 的唯一实质区别。

商业授权解除的正是这两条义务：你可以闭源分发、闭源托管，不必公开你的修改。

---

## 价格

以下价格自 2026-08-01 起有效，按**单一法人实体**计，不限内部使用人数、不限机器数。

| 授权 | 覆盖范围 | 价格 |
|---|---|---|
| **嵌入授权** | 一条产品线的闭源分发，或一个对外网络服务。含一年内的版本升级 | **¥60,000 / 年** |
| **企业授权** | 不限产品线与服务数量，含子公司。含一年内的版本升级 | **¥150,000 / 年** |
| **买断** | 签约时最新版本的永久闭源使用权，不含后续版本 | **¥300,000 一次性** |
| **支持 SLA**（可选，需先有上述任一授权） | 工作日 4 小时内首次响应，含版本兼容性问题定位 | **¥40,000 / 年** |

附带说明：

- 授权覆盖**本仓库的代码**。它不给你任何求解器的授权 —— Abaqus 的授权你要向
  Dassault Systèmes 买。本项目只是定位并调用它（见 NOTICE），不分发、不捆绑
  任何求解器
- 年费到期不续：已交付的版本可以继续用，停止获得新版本
- 学术机构、注册在案的开源非营利项目：情形 A/B 也免费，写邮件说明用途即可
- 需要发票、需要中文书面合同、需要走对公 —— 都可以，邮件说明

---

## 贡献者须知（inbound = Apache-2.0）

向本仓库提交的代码按 **Apache-2.0** 授权（见 `CONTRIBUTING.md`），而项目对外
以 AGPL-3.0-or-later 发布。这是刻意的：Apache-2.0 第 2 条授予再许可权，
因此不需要你签 CLA、不需要转让版权，而项目方仍可提供上面的商业授权。

你的贡献同时永远保留在 Apache-2.0 之下，任何人都可以从原始提交处按 Apache-2.0
取用。历史与致谢见 `NOTICE`。

---

## 其它许可证

- `schema/`、`cases/`、`examples/` 是 **Apache-2.0**（见 `NOTICE`）。
  对接用的契约必须能被自由抄走，否则没人会来对接
- 公开发布的课程与文章材料是 **CC BY 4.0**，署名即可转载。这些内容不在本仓库内
- 第三方组件见 `THIRD_PARTY_NOTICES.md`

---

# Licensing (English)

Abaqus Agent is dual-licensed: **AGPL-3.0-or-later**, or a commercial licence.
Contact: zhaoshaofeng892@gmail.com (subject line `[licensing]`).

**Most users do not need to buy anything.** Using this under the AGPL is free,
including commercially. Running it inside your company, modifying it, and
delivering the *results* to your clients triggers no obligation at all.

You need a commercial licence in exactly two cases:

- **A — Closed distribution.** You ship this (or a derivative, or a product
  containing it) outside your organisation without offering the recipients the
  corresponding source.
- **B — Network service.** You offer it to users over a network without
  offering those users the corresponding source. This is AGPL §13.

| Licence | Scope | Price |
|---|---|---|
| Embedded | One product line, or one network service. Includes one year of updates | **CNY 60,000 / year** |
| Enterprise | Unlimited product lines and services, subsidiaries included. Includes one year of updates | **CNY 150,000 / year** |
| Perpetual | Permanent closed-source use of the version current at signing; no future versions | **CNY 300,000 one-off** |
| Support SLA (optional add-on) | First response within 4 business hours | **CNY 40,000 / year** |

A commercial licence covers *this repository's code only*. It grants no rights
to any solver: Abaqus is licensed by Dassault Systèmes, and this project
neither bundles nor redistributes it — it locates and invokes whatever the user
installed. See `NOTICE`.

Free for academic use and for registered open-source non-profits, in cases A
and B alike. Just email and say what it is for.
