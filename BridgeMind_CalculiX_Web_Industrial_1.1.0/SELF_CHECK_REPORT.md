# BridgeMind Studio 1.1.0 + BSDL Industrial 1.0 自检报告

结果：8 项通过，0 项失败。

## PASS · JSON Schema 元验证

```json
{
  "definitionCount": 27,
  "schemaId": "https://example.org/bridgemind/bsdl/0.1.0/bsdl.schema.json"
}
```

## PASS · 正式示例验证

```json
{
  "two_girder_bridge.bsdl.json": {
    "level": "L4-valid",
    "stats": {
      "entities": 51,
      "nodes": 10,
      "components": 14,
      "activeFrameComponents": 13,
      "regions": 0,
      "loads": 6,
      "constrainedDofs": 14,
      "validLoads": 6,
      "coordinateSystems": 1,
      "componentLengthMin": 6.0,
      "componentLengthMax": 10.0
    }
  },
  "cantilever_3d.bsdl.json": {
    "level": "L4-valid",
    "stats": {
      "entities": 14,
      "nodes": 2,
      "components": 1,
      "activeFrameComponents": 1,
      "regions": 0,
      "loads": 1,
      "constrainedDofs": 6,
      "validLoads": 1,
      "coordinateSystems": 1,
      "componentLengthMin": 8.774964387392123,
      "componentLengthMax": 8.774964387392123
    }
  }
}
```

## PASS · 多专家认知与快速 FEA

```json
{
  "initialRegions": 24,
  "feedbackRegions": 26,
  "hotspots": 2,
  "landmarks": 26,
  "mesh": {
    "nodeCount": 154,
    "elementCount": 157,
    "componentCount": 13,
    "minElementLength": 0.09999999999999964,
    "maxElementLength": 1.2166666666666686,
    "meanElementLength": 0.7006369426751592,
    "meshPolicyRef": "mesh.default",
    "baseSize": 1.25
  },
  "globalMetrics": {
    "maxTranslation": 0.04095873788152383,
    "maxVerticalDisplacement": 0.04095873788152383,
    "maxAxial": 0.0,
    "maxShear": 300000.0009765625,
    "maxMoment": 4500000.004732132,
    "forceBalanceResidual": 0.0001430511474609375,
    "relativeForceBalanceResidual": 1.1920928955078125e-10,
    "conditionNumber": 6350153822.825311,
    "dofCount": 924,
    "freeDofCount": 910,
    "constrainedDofCount": 14,
    "loadCaseRef": "lc.service",
    "wallSeconds": 0.2755318529999897
  }
}
```

## PASS · 修订—反馈—经验—Adapter 闭环

```json
{
  "seededProjects": 3,
  "seededTemplates": 4,
  "strategyRevision": 2,
  "feedbackRevision": 3,
  "runStatus": "succeeded",
  "experienceCount": 27,
  "revisionCount": 3,
  "templateCount": 4,
  "exportAdapters": [
    "bsdl",
    "gmsh",
    "calculix"
  ]
}
```

## PASS · 跨项目经验读回链

```json
{
  "acceptedExperienceCount": 1,
  "matchedRegionCount": 4,
  "appliedRegionCount": 4,
  "usedExperienceIds": [
    "experience.b0b623326afa53bbb2dfc12b"
  ],
  "baselineSupportActions": [
    [
      "support",
      0.5625,
      5
    ],
    [
      "support",
      0.5625,
      5
    ],
    [
      "support",
      0.5625,
      5
    ],
    [
      "support",
      0.5625,
      5
    ]
  ],
  "inheritedSupportActions": [
    [
      "support",
      0.28125,
      7
    ],
    [
      "support",
      0.28125,
      7
    ],
    [
      "support",
      0.28125,
      7
    ],
    [
      "support",
      0.28125,
      7
    ]
  ]
}
```

## PASS · 点云分割到 BSDL

```json
{
  "inputPoints": 6100,
  "sampledPoints": 3694,
  "clusters": 3,
  "components": 4,
  "validationLevel": "L4-valid"
}
```

## PASS · FastAPI 与 Web 资源

```json
{
  "health": {
    "status": "ok",
    "version": "1.1.0",
    "languageVersion": "1.0.0",
    "projects": 3
  },
  "projectCount": 3,
  "templateCount": 4,
  "htmlBytes": 13900,
  "javascriptBytes": 103749,
  "stylesheetBytes": 17601
}
```

## PASS · JavaScript 语法

```json
{
  "node": "/usr/local/bin/node",
  "file": "web/app.js",
  "bytes": 103749
}
```
