"""Shared evaluator for the MegaOrder endpoint-assignment objective."""


def _edges_of(tunnel):
    return zip(tunnel[:-1], tunnel[1:])


def evaluate_assignment_objective(assignment, previous_assignment, tm, graph,
                                  epsilon=0.1, loss_weight=0.5):
    """Evaluate the exact solver's objective on any method's deployment.

    ``assignment`` and ``previous_assignment`` map endpoint pairs ``(i, j)``
    to site-level tunnel tuples.  A pair contributes reordered loss only when
    it is assigned in both rounds and its tunnel changed.
    """
    epsilon = float(epsilon)
    loss_weight = float(loss_weight)
    previous_assignment = previous_assignment or {}
    tunnel_weight = {}
    satisfied_demand = 0.0
    weight_penalty = 0.0
    loss_value = 0.0
    reordered_pairs = 0

    for pair, tunnel in assignment.items():
        demand = float(tm[pair[0], pair[1]])
        satisfied_demand += demand

        weight = tunnel_weight.get(tunnel)
        if weight is None:
            weight = sum(1.0 / graph[u][v]['capacity']
                         for u, v in _edges_of(tunnel))
            tunnel_weight[tunnel] = weight
        weight_penalty += epsilon * weight * demand

        previous_tunnel = previous_assignment.get(pair)
        if previous_tunnel is not None and previous_tunnel != tunnel:
            loss_value += demand
            reordered_pairs += 1

    obj_val = (satisfied_demand - weight_penalty -
               loss_weight * loss_value)
    return {
        'obj_val': obj_val,
        'satisfied_demand': satisfied_demand,
        'weight_penalty': weight_penalty,
        'loss_value': loss_value,
        'reordered_pairs': reordered_pairs,
        'epsilon': epsilon,
        'loss_weight': loss_weight,
    }
