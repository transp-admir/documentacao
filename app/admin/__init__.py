from flask import Blueprint

# Define o Blueprint para a área administrativa
# Sem o 'template_folder', o Flask procurará os templates em app/templates/admin/
admin_bp = Blueprint(
    'admin',
    __name__,
    url_prefix='/admin'
)

from . import routes
