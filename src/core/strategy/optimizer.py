"""
策略参数优化模块
支持贝叶斯优化、遗传算法、网格搜索
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Callable, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import logging
import random

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict[str, Any]
    best_score: float
    iterations: int
    elapsed_seconds: float
    algorithm: str
    all_results: List[Dict] = field(default_factory=list)


@dataclass
class ParameterSpace:
    """参数空间定义"""
    name: str
    min_value: float
    max_value: float
    step: Optional[float] = None  # 网格搜索步长
    discrete: bool = False  # 是否离散值
    values: Optional[List[Any]] = None  # 离散值列表


class ObjectiveFunction:
    """目标函数包装器"""

    def __init__(
        self,
        func: Callable[[Dict], float],
        maximize: bool = True,
        penalty_func: Callable[[Dict], float] = None
    ):
        """
        Args:
            func: 目标函数 (params) -> score
            maximize: 是否最大化
            penalty_func: 惩罚函数（用于约束）
        """
        self.func = func
        self.maximize = maximize
        self.penalty_func = penalty_func

    def evaluate(self, params: Dict) -> float:
        """评估参数"""
        try:
            score = self.func(params)
            
            # 应用惩罚
            if self.penalty_func:
                penalty = self.penalty_func(params)
                score = score - penalty
            
            return score if self.maximize else -score
        except Exception as e:
            logger.debug(f"Objective evaluation failed: {e}")
            return float('-inf') if self.maximize else float('inf')


class GridSearchOptimizer:
    """网格搜索优化器"""

    def __init__(self, n_jobs: int = 1):
        self.n_jobs = n_jobs

    def optimize(
        self,
        param_spaces: Dict[str, ParameterSpace],
        objective: ObjectiveFunction,
        max_combinations: int = 10000,
        timeout_seconds: float = None
    ) -> OptimizationResult:
        """
        网格搜索优化
        
        Args:
            param_spaces: 参数空间字典
            objective: 目标函数
            max_combinations: 最大组合数
            timeout_seconds: 超时时间
        
        Returns:
            OptimizationResult
        """
        start_time = datetime.now()
        
        # 生成参数组合
        param_names = list(param_spaces.keys())
        param_values = []
        
        for name, space in param_spaces.items():
            if space.values:
                values = space.values
            elif space.step:
                values = np.arange(space.min_value, space.max_value + space.step, space.step)
                if space.discrete:
                    values = [int(v) for v in values]
            else:
                # 均匀采样
                n_samples = min(10, max_combinations ** (1 / len(param_spaces)))
                values = np.linspace(space.min_value, space.max_value, int(n_samples))
            
            param_values.append(values)
        
        # 计算总组合数
        total_combinations = 1
        for values in param_values:
            total_combinations *= len(values)
        
        if total_combinations > max_combinations:
            logger.warning(f"Total combinations {total_combinations} > {max_combinations}, sampling")
            # 随机采样
            all_params = []
            for _ in range(max_combinations):
                params = {name: random.choice(values) for name, values in zip(param_names, param_values)}
                all_params.append(params)
        else:
            # 全组合
            import itertools
            all_params = [dict(zip(param_names, combo)) for combo in itertools.product(*param_values)]
        
        # 并行评估
        results = []
        
        if self.n_jobs > 1:
            with ThreadPoolExecutor(max_workers=self.n_jobs) as executor:
                futures = {executor.submit(objective.evaluate, params): params for params in all_params}
                for future in as_completed(futures, timeout=timeout_seconds):
                    params = futures[future]
                    try:
                        score = future.result()
                        results.append({"params": params, "score": score})
                    except Exception as e:
                        logger.debug(f"Evaluation failed for {params}: {e}")
        else:
            for params in all_params:
                score = objective.evaluate(params)
                results.append({"params": params, "score": score})
        
        # 找最优
        best_result = max(results, key=lambda x: x["score"])
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return OptimizationResult(
            best_params=best_result["params"],
            best_score=best_result["score"],
            all_results=results,
            iterations=len(all_params),
            elapsed_seconds=elapsed,
            algorithm="grid_search"
        )


class GeneticAlgorithmOptimizer:
    """遗传算法优化器"""

    def __init__(
        self,
        population_size: int = 50,
        n_generations: int = 100,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.1,
        elite_ratio: float = 0.1,
        n_jobs: int = 1
    ):
        self.population_size = population_size
        self.n_generations = n_generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.elite_ratio = elite_ratio
        self.n_jobs = n_jobs

    def _init_population(
        self,
        param_spaces: Dict[str, ParameterSpace]
    ) -> List[Dict]:
        """初始化种群"""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for name, space in param_spaces.items():
                if space.values:
                    individual[name] = random.choice(space.values)
                else:
                    individual[name] = random.uniform(space.min_value, space.max_value)
                    if space.discrete:
                        individual[name] = int(individual[name])
            population.append(individual)
        return population

    def _mutate(
        self,
        individual: Dict,
        param_spaces: Dict[str, ParameterSpace]
    ) -> Dict:
        """变异"""
        mutated = individual.copy()
        for name, space in param_spaces.items():
            if random.random() < self.mutation_rate:
                if space.values:
                    mutated[name] = random.choice(space.values)
                else:
                    value = random.uniform(space.min_value, space.max_value)
                    if space.discrete:
                        value = int(value)
                    mutated[name] = value
        return mutated

    def _crossover(
        self,
        parent1: Dict,
        parent2: Dict,
        param_spaces: Dict[str, ParameterSpace]
    ) -> Dict:
        """交叉"""
        if random.random() > self.crossover_rate:
            return parent1.copy()
        
        child = {}
        for name in param_spaces.keys():
            if random.random() < 0.5:
                child[name] = parent1[name]
            else:
                child[name] = parent2[name]
        
        return child

    def optimize(
        self,
        param_spaces: Dict[str, ParameterSpace],
        objective: ObjectiveFunction,
        timeout_seconds: float = None
    ) -> OptimizationResult:
        """
        遗传算法优化
        
        Args:
            param_spaces: 参数空间
            objective: 目标函数
            timeout_seconds: 超时
        
        Returns:
            OptimizationResult
        """
        start_time = datetime.now()
        
        # 初始化种群
        population = self._init_population(param_spaces)
        
        # 评估种群
        def evaluate_individual(ind):
            return {"params": ind, "score": objective.evaluate(ind)}
        
        if self.n_jobs > 1:
            with ThreadPoolExecutor(max_workers=self.n_jobs) as executor:
                evaluated = list(executor.map(evaluate_individual, population))
        else:
            evaluated = [evaluate_individual(ind) for ind in population]
        
        best_result = max(evaluated, key=lambda x: x["score"])
        all_results = evaluated.copy()
        
        # 进化
        for gen in range(self.n_generations):
            # 选择精英
            n_elite = int(self.population_size * self.elite_ratio)
            elite = sorted(evaluated, key=lambda x: x["score"], reverse=True)[:n_elite]
            
            # 生成新种群
            new_population = [e["params"] for e in elite]
            
            while len(new_population) < self.population_size:
                # 锦标赛选择
                tournament = random.sample(evaluated, k=3)
                winner = max(tournament, key=lambda x: x["score"])["params"]
                
                # 随机选择另一个
                other = random.choice(evaluated)["params"]
                
                # 交叉
                child = self._crossover(winner, other, param_spaces)
                
                # 变异
                child = self._mutate(child, param_spaces)
                
                new_population.append(child)
            
            population = new_population[:self.population_size]
            
            # 评估
            if self.n_jobs > 1:
                with ThreadPoolExecutor(max_workers=self.n_jobs) as executor:
                    evaluated = list(executor.map(evaluate_individual, population))
            else:
                evaluated = [evaluate_individual(ind) for ind in population]
            
            gen_best = max(evaluated, key=lambda x: x["score"])
            all_results.extend(evaluated)
            
            if gen_best["score"] > best_result["score"]:
                best_result = gen_best
            
            logger.info(f"Generation {gen+1}: best={best_result['score']:.4f}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return OptimizationResult(
            best_params=best_result["params"],
            best_score=best_result["score"],
            all_results=all_results,
            iterations=self.n_generations,
            elapsed_seconds=elapsed,
            algorithm="genetic_algorithm"
        )


class BayesianOptimizer:
    """贝叶斯优化器（简化版，基于高斯过程）"""

    def __init__(
        self,
        n_iterations: int = 50,
        n_initial_points: int = 10,
        exploration_ratio: float = 0.1,
        n_jobs: int = 1
    ):
        self.n_iterations = n_iterations
        self.n_initial_points = n_initial_points
        self.exploration_ratio = exploration_ratio
        self.n_jobs = n_jobs

    def _get_param_bounds(self, param_spaces: Dict[str, ParameterSpace]) -> Dict:
        """获取参数边界"""
        bounds = {}
        for name, space in param_spaces.items():
            bounds[name] = (space.min_value, space.max_value)
        return bounds

    def _sample_random_params(self, param_spaces: Dict[str, ParameterSpace]) -> Dict:
        """随机采样参数"""
        params = {}
        for name, space in param_spaces.items():
            if space.values:
                params[name] = random.choice(space.values)
            else:
                params[name] = random.uniform(space.min_value, space.max_value)
                if space.discrete:
                    params[name] = int(params[name])
        return params

    def _gaussian_acquisition(
        self,
        X: np.ndarray,
        y: np.ndarray,
        x_test: np.ndarray,
        bounds: Dict
    ) -> float:
        """
        计算采集函数（UCB - Upper Confidence Bound）
        
        简化版：使用基于距离的探索奖励
        """
        if len(y) < 2:
            return random.random()  # 随机探索
        
        # 计算到最近邻居的距离（探索奖励）
        min_dist = float('inf')
        for x in X:
            dist = np.linalg.norm(x_test - x)
            min_dist = min(min_dist, dist)
        
        # 探索奖励
        exploration_bonus = min_dist * self.exploration_ratio
        
        # 利用奖励（基于历史最优）
        best_y = max(y)
        current_y = np.interp(
            x_test[0],
            [bounds[k][0] for k in bounds.keys()],
            [0, 1]
        ) * best_y
        
        return exploration_bonus + current_y

    def optimize(
        self,
        param_spaces: Dict[str, ParameterSpace],
        objective: ObjectiveFunction,
        timeout_seconds: float = None
    ) -> OptimizationResult:
        """
        贝叶斯优化
        
        Args:
            param_spaces: 参数空间
            objective: 目标函数
            timeout_seconds: 超时
        
        Returns:
            OptimizationResult
        """
        start_time = datetime.now()
        bounds = self._get_param_bounds(param_spaces)
        param_names = list(bounds.keys())
        
        # 初始随机采样
        initial_params = [self._sample_random_params(param_spaces) for _ in range(self.n_initial_points)]
        
        results = []
        X_history = []
        y_history = []
        
        # 评估初始点
        for params in initial_params:
            score = objective.evaluate(params)
            results.append({"params": params, "score": score})
            
            # 转换为数值向量
            x_vec = np.array([[params.get(name, 0) for name in param_names]])
            X_history.append(x_vec)
            y_history.append(score)
        
        X_history = np.vstack(X_history) if len(X_history) > 0 else np.array([]).reshape(0, len(param_names))
        y_history = np.array(y_history)
        
        best_result = max(results, key=lambda x: x["score"])
        
        # 迭代优化
        for i in range(self.n_iterations - self.n_initial_points):
            # 生成候选点（在边界内随机采样）
            candidates = [self._sample_random_params(param_spaces) for _ in range(20)]
            
            # 计算每个候选点的采集函数值
            best_candidate = None
            best_acquisition = float('-inf')
            
            for candidate in candidates:
                x_vec = np.array([[candidate.get(name, 0) for name in param_names]])
                
                # 计算采集函数（简化版）
                if len(y_history) > 0:
                    # UCB: 探索 + 利用
                    exploitation = max(y_history)  # 利用部分
                    
                    # 探索：距离最近观察点的距离
                    if len(X_history) > 0:
                        distances = np.linalg.norm(X_history - x_vec, axis=1)
                        exploration = np.max(distances) * self.exploration_ratio
                    else:
                        exploration = 1.0
                    
                    acquisition = exploitation + exploration
                else:
                    acquisition = random.random()
                
                if acquisition > best_acquisition:
                    best_acquisition = acquisition
                    best_candidate = candidate
            
            # 评估最优候选点
            if best_candidate:
                score = objective.evaluate(best_candidate)
                results.append({"params": best_candidate, "score": score})
                
                x_vec = np.array([[best_candidate.get(name, 0) for name in param_names]])
                X_history = np.vstack([X_history, x_vec]) if len(X_history) > 0 else x_vec
                y_history = np.append(y_history, score)
                
                if score > best_result["score"]:
                    best_result = {"params": best_candidate, "score": score}
            
            logger.info(f"Bayesian iteration {i+1}/{self.n_iterations - self.n_initial_points}: best={best_result['score']:.4f}")
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        return OptimizationResult(
            best_params=best_result["params"],
            best_score=best_result["score"],
            all_results=results,
            iterations=self.n_iterations,
            elapsed_seconds=elapsed,
            algorithm="bayesian_optimization"
        )


def create_optimizer(
    algorithm: str = "bayesian",
    n_jobs: int = 1,
    **kwargs
) -> Any:
    """
    创建优化器工厂函数
    
    Args:
        algorithm: "grid_search" | "genetic" | "bayesian"
        n_jobs: 并行数
        **kwargs: 其他参数
    
    Returns:
        优化器实例
    """
    if algorithm == "grid_search":
        return GridSearchOptimizer(n_jobs=n_jobs)
    elif algorithm == "genetic":
        return GeneticAlgorithmOptimizer(n_jobs=n_jobs, **kwargs)
    elif algorithm == "bayesian":
        return BayesianOptimizer(n_jobs=n_jobs, **kwargs)
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")


def optimize_strategy_parameters(
    param_spaces: Dict[str, ParameterSpace],
    backtest_func: Callable[[Dict], float],
    algorithm: str = "bayesian",
    maximize: bool = True,
    penalty_func: Callable[[Dict], float] = None,
    timeout_seconds: float = None,
    **optimizer_kwargs
) -> OptimizationResult:
    """
    便捷函数：优化策略参数
    
    Args:
        param_spaces: 参数空间定义
        backtest_func: 回测函数 (params) -> score
        algorithm: 优化算法
        maximize: 是否最大化目标
        penalty_func: 惩罚函数
        timeout_seconds: 超时时间
        **optimizer_kwargs: 优化器参数
    
    Returns:
        OptimizationResult
    """
    optimizer = create_optimizer(algorithm, **optimizer_kwargs)
    objective = ObjectiveFunction(backtest_func, maximize=maximize, penalty_func=penalty_func)
    
    return optimizer.optimize(param_spaces, objective, timeout_seconds=timeout_seconds)