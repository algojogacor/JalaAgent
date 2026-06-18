---
name: data-analysis
description: pandas, numpy, statistical analysis, data visualization with matplotlib/seaborn. Insight extraction from structured data.
version: 1.0.0
author: JalaAgent
license: Apache-2.0
platforms: [windows, linux, macos, termux]
metadata:
  jalaagent:
    always: false
    emoji: 📊
    requires: {bins: [python], env: []}
---

# Data Analysis

## Overview
Analyze structured data (CSV, JSON, SQL). Extract insights, visualize patterns, report findings.

## Process
1. Load: `pd.read_csv()`, handle encoding and date parsing
2. Clean: drop duplicates, fill/remove nulls, fix dtypes
3. Explore: `.describe()`, `.info()`, `.value_counts()`
4. Analyze: groupby, pivot, correlation matrix
5. Visualize: matplotlib/seaborn with labels and titles
6. Report: one insight per paragraph, supported by data

## Visualization Rules
- Bar chart for categories, line for trends, scatter for correlation
- Always label axes (with units if applicable)
- Title must state the insight, not just describe the chart
- Use color deliberately, not decoratively

## Anti-Patterns
- Don't jump to visualization before understanding the data
- Don't use pie charts for more than 5 categories
- Don't report correlations without checking causation
