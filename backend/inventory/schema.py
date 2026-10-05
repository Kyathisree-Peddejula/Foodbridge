from drf_spectacular.extensions import OpenApiAuthenticationExtension


class POSKeyScheme(OpenApiAuthenticationExtension):
    target_class = "inventory.pos_auth.POSKeyAuthentication"
    name = "POSKey"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-POS-Key",
                "description": "Key created under POST /api/pos/integrations/"}
