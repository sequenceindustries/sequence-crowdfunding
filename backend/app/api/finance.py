from flask import Blueprint, jsonify, request

from ..security import roles_required
from ..services.finance import FinanceInputError, check_consistency, project

bp = Blueprint("finance", __name__, url_prefix="/api/finance")


def _run(fn):
    try:
        return jsonify(fn(request.get_json(silent=True))), 200
    except FinanceInputError as exc:
        return jsonify(error="invalid_input", message=str(exc)), 400


@bp.post("/projection")
@roles_required("founder")
def projection():
    """Stateless: nothing the founder enters here is stored."""
    return _run(project)


@bp.post("/consistency")
@roles_required("founder")
def consistency():
    return _run(check_consistency)
