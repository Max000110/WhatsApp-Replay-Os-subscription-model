# Platform Branding & Visual Identity Guide

This document details the visual identity, brand guidelines, color system, typography, and styling tokens for the WhatsApp AI SaaS platform dashboard.

---

## 1. Brand Concept & Messaging

* **Brand Name**: **WhatsAppFlow AI / WA-SaaS**
* **Tagline**: *Private, Cost-Efficient WhatsApp AI Automation at Scale.*
* **Voice**: Professional, secure, highly reliable, developer-friendly, and modern.
* **Target Audience**: SMBs, digital agencies, customer service providers, and SaaS startups wanting full control over customer conversation pipelines without high recurring costs.

---

## 2. Visual Palette (CSS Hex Tokens)

The dashboard uses a premium modern dark theme with emerald and violet accents. Below is the CSS theme configuration matching Tailwind or standard CSS variables:

### Primary Colors
* **Primary Deep Violet (Accents)**: `#6D28D9` (HSL `263, 84%, 51%`)
* **Primary Light Emerald (WhatsApp Accents)**: `#10B981` (HSL `162, 76%, 41%`)
* **Secondary Slate Indigo**: `#4F46E5` (HSL `239, 84%, 60%`)

### Neutral Theme Tones
* **Dark Background (Main Canvas)**: `#0F172A` (Slate-900)
* **Dark Background (Cards / Modals)**: `#1E293B` (Slate-800)
* **Border Lines / Dividers**: `#334155` (Slate-700)
* **Neutral Off-white (Text Primary)**: `#F8FAFC` (Slate-50)
* **Neutral Gray (Text Secondary)**: `#94A3B8` (Slate-400)
* **Alert Danger (Errors)**: `#EF4444` (Red-500)

---

## 3. Typography & Text Hierarchy

We leverage high-legibility sans-serif sans-serif faces:
* **Primary Font Face**: **Inter** (via Google Fonts) - used for tables, sidebar options, and body text.
* **Header Font Face**: **Outfit** or **Cabinet Grotesk** - used for dashboard main headers, metrics statistics numbers, and pricing tier names.

### Hierarchy
* `h1`: `font-size: 2.25rem (36px)`, `font-weight: 700 (bold)`, `font-family: 'Outfit'`
* `h2`: `font-size: 1.5rem (24px)`, `font-weight: 600 (semi-bold)`, `font-family: 'Outfit'`
* `h3`: `font-size: 1.25rem (20px)`, `font-weight: 600`, `font-family: 'Inter'`
* `body`: `font-size: 0.875rem (14px)`, `font-weight: 400`, `font-family: 'Inter'`, `color: #F8FAFC`

---

## 4. UI Elements Style System

* **Glassmorphism Layering**:
  Card structures should use a combination of transparent backgrounds, back-drop filters, and subtle slate borders:
  ```css
  background-color: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(51, 65, 85, 0.5);
  border-radius: 12px;
  ```
* **Dynamic Hover States**:
  Any interactive item (Sidebar tabs, buttons, quick replies) must animate smoothly upon cursor hover with HSL color transitions:
  ```css
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  ```
* **Status Badge Indicators**:
  * Connected Session: Emerald background pulse (`bg-emerald-500/10 text-emerald-400 border-emerald-500/30`)
  * Disconnected Session: Rose background pulse (`bg-rose-500/10 text-rose-400 border-rose-500/30`)
  * Scan Pending Session: Amber background pulse (`bg-amber-500/10 text-amber-400 border-amber-500/30`)
