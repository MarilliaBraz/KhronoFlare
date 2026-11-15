"""Modelo de mês crítico e validação (passo 4).

Random Forest sobre o painel (histórico, climatologia, posição, sazonalidade, bioma e, no modelo
escolhido, ONI). Duas validações:

  * temporal: treino nos anos-alvo 2004–2016, teste em 2017–2021;
  * espacial: blocos de `block_deg` graus repartidos em grupos; cada grupo sai do treino e é avaliado
    só nos anos de teste (região e anos novos ao mesmo tempo). A climatologia de uma célula deixada de
    fora vem dos anos de treino dela mesma: testa-se a generalização do aprendizado para outra região,
    não o caso de uma célula sem nenhum histórico.

Referências: sorteio (0,5), "repetir o mês atual" (ΣFRP do mês t como pontuação) e climatologia
(probabilidade de fogo naquela célula e mês do ano, anos de treino).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from .drivers import BIOME_CODES
from .panel import FEATURES

BASE_FEATURES = [*FEATURES, *[f"bioma_{c}" for c in BIOME_CODES]]
ONI_FEATURES = [*BASE_FEATURES, "oni_atual", "oni_3m"]
TARGET = "y_critico"
MIN_SAMPLES_LEAF = 20

# Grupos para a importância por permutação (passo 5): variáveis correlacionadas são embaralhadas juntas.
FEATURE_GROUPS = {
    "historico_recente": ["n_lag0", "n_lag1", "n_lag2", "frp_lag0", "frp_lag1", "frp_lag2"],
    "ano_anterior_e_12m": ["n_mesmo_mes_ano_ant", "n_12m"],
    "climatologia": ["p_fogo", "n_med"],
    "posicao": ["cy", "cx"],
    "sazonalidade": ["mes_sin", "mes_cos"],
    "bioma": [f"bioma_{c}" for c in BIOME_CODES],
}


def make_model(n_estimators: int = 200, seed: int = 0) -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=n_estimators, min_samples_leaf=MIN_SAMPLES_LEAF,
                                  n_jobs=-1, random_state=seed)


def evaluate(y, score) -> dict:
    """ROC-AUC e PR-AUC (NaN se só houver uma classe); Brier só quando a pontuação é probabilidade."""
    y, score = np.asarray(y, dtype=int), np.asarray(score, dtype=float)
    both = 0 < y.sum() < len(y)
    is_prob = bool(len(score)) and score.min() >= 0 and score.max() <= 1
    return {
        "n": int(len(y)),
        "prevalencia": float(y.mean()) if len(y) else float("nan"),
        "roc_auc": float(roc_auc_score(y, score)) if both else float("nan"),
        "pr_auc": float(average_precision_score(y, score)) if both else float("nan"),
        "brier": float(brier_score_loss(y, score)) if is_prob else float("nan"),
    }


def _check(panel: pd.DataFrame, features: list[str]) -> None:
    missing = [c for c in [*features, TARGET] if c not in panel.columns]
    if missing:
        raise ValueError(f"painel sem as variáveis {missing}")


def _references(test: pd.DataFrame) -> dict:
    return {"sorteio": np.full(len(test), 0.5),
            "repetir_mes_atual": test["frp_lag0"].to_numpy(float),
            "climatologia": test["p_fogo"].to_numpy(float)}


def _by(groups, y: np.ndarray, p: np.ndarray) -> dict:
    groups = np.asarray(groups).astype(str)
    return {g: evaluate(y[groups == g], p[groups == g]) for g in np.unique(groups)}


def _kind(test: pd.DataFrame) -> np.ndarray:
    """fora_de_epoca: célula sem fogo típico naquele mês (p75 = 0); temporada: época pior que o normal."""
    return np.where(test["frp_p75"].to_numpy() == 0, "fora_de_epoca", "temporada")


def fit_model(panel: pd.DataFrame, features: list[str], train_years: tuple[int, int],
              n_estimators: int = 200, seed: int = 0) -> RandomForestClassifier:
    """Ajusta o Random Forest nos anos-alvo de treino."""
    _check(panel, features)
    tr = panel[panel["ano_alvo"].between(*train_years)]
    return make_model(n_estimators, seed).fit(tr[features], tr[TARGET])


def temporal_validation(panel: pd.DataFrame, features: list[str], train_years: tuple[int, int],
                        test_years: tuple[int, int], n_estimators: int = 200, seed: int = 0) -> dict:
    model = fit_model(panel, features, train_years, n_estimators, seed)
    tr = panel[panel["ano_alvo"].between(*train_years)]
    te = panel[panel["ano_alvo"].between(*test_years)]
    p = model.predict_proba(te[features])[:, 1]
    y = te[TARGET].to_numpy()
    return {
        "variaveis": list(features),
        "treino": {"anos": list(train_years), "linhas": int(len(tr)), "prevalencia": float(tr[TARGET].mean())},
        "teste": {
            "anos": list(test_years), "linhas": int(len(te)),
            "modelo": evaluate(y, p),
            "referencias": {k: evaluate(y, s) for k, s in _references(te).items()},
            "por_ano": _by(te["ano_alvo"], y, p),
            "por_bioma": _by(te["bioma"], y, p),
            "por_tipo": _by(_kind(te), y, p),
        },
    }


def _blocks(panel: pd.DataFrame, block_deg: float, res: float) -> np.ndarray:
    by = np.floor((panel["cy"].to_numpy() + 0.5) * res / block_deg).astype(int)
    bx = np.floor((panel["cx"].to_numpy() + 0.5) * res / block_deg).astype(int)
    return np.char.add(np.char.add(by.astype(str), "_"), bx.astype(str))


def spatial_folds(panel: pd.DataFrame, block_deg: float, res: float, n_folds: int,
                  seed: int = 0) -> list[tuple[np.ndarray, np.ndarray]]:
    """Grupos de blocos de `block_deg` graus: (máscara de treino, máscara de teste) por grupo."""
    blocks = _blocks(panel, block_deg, res)
    unique = np.unique(blocks)
    if len(unique) < n_folds:
        raise ValueError(f"só {len(unique)} blocos de {block_deg}° para {n_folds} grupos")
    shuffled = np.random.default_rng(seed).permutation(unique)
    folds = []
    for group in np.array_split(shuffled, n_folds):
        test_mask = np.isin(blocks, group)
        folds.append((~test_mask, test_mask))
    return folds


def spatial_validation(panel: pd.DataFrame, features: list[str], train_years: tuple[int, int],
                       test_years: tuple[int, int], block_deg: float, res: float, n_folds: int = 5,
                       n_estimators: int = 200, seed: int = 0) -> dict:
    _check(panel, features)
    in_train = panel["ano_alvo"].between(*train_years).to_numpy()
    in_test = panel["ano_alvo"].between(*test_years).to_numpy()
    pred = np.full(len(panel), np.nan)
    groups = []
    for i, (train_mask, test_mask) in enumerate(spatial_folds(panel, block_deg, res, n_folds, seed)):
        tr, te = panel[train_mask & in_train], panel[test_mask & in_test]
        model = make_model(n_estimators, seed).fit(tr[features], tr[TARGET])
        pred[test_mask & in_test] = model.predict_proba(te[features])[:, 1]
        groups.append({"grupo": i, "celulas": int(te[["cy", "cx"]].drop_duplicates().shape[0]),
                       **evaluate(te[TARGET], pred[test_mask & in_test])})
    te_all = panel[in_test]
    y = te_all[TARGET].to_numpy()
    return {
        "blocos_graus": block_deg, "grupos": n_folds,
        "teste": {"anos": list(test_years), "linhas": int(in_test.sum()),
                  "modelo": evaluate(y, pred[in_test]),
                  "referencias": {k: evaluate(y, s) for k, s in _references(te_all).items()}},
        "por_grupo": groups,
    }


def grouped_permutation_importance(model: RandomForestClassifier, test: pd.DataFrame, features: list[str],
                                   groups: dict, n_repeats: int = 5, seed: int = 0) -> pd.DataFrame:
    """Queda média do ROC-AUC no teste ao embaralhar juntas as colunas de cada grupo (não altera `test`)."""
    x = test[features].to_numpy(dtype=float)
    y = test[TARGET].to_numpy()
    base = roc_auc_score(y, model.predict_proba(pd.DataFrame(x, columns=features))[:, 1])
    rng = np.random.default_rng(seed)
    rows = {}
    for name, cols in groups.items():
        idx = [features.index(c) for c in cols if c in features]
        drops = []
        for _ in range(n_repeats):
            shuffled = x.copy()
            shuffled[:, idx] = x[rng.permutation(len(x))][:, idx]
            auc = roc_auc_score(y, model.predict_proba(pd.DataFrame(shuffled, columns=features))[:, 1])
            drops.append(base - auc)
        rows[name] = {"queda_auc": float(np.mean(drops)), "desvio": float(np.std(drops))}
    return pd.DataFrame(rows).T.sort_values("queda_auc", ascending=False)
