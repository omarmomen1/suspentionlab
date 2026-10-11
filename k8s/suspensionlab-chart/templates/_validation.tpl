{{/*
Pre-Deployment Production Secrets & Configuration Validator
Ensures production configuration strictly rejects:
  - REPLACE_WITH_
  - changeme
  - default
  - example
*/}}
{{- $isProd := or (eq (.Values.environment | default "") "production") (eq (.Values.environment | default "") "prod") -}}
{{- if $isProd -}}
  {{- if not .Values.externalSecrets.enabled -}}
    {{- range $k, $v := .Values.secrets -}}
      {{- if or (contains "REPLACE_WITH_" $v) (contains "changeme" $v) (contains "default" $v) (contains "example" $v) -}}
        {{- fail (printf "PRE-DEPLOYMENT SECURITY VIOLATION: Secret %s contains prohibited placeholder pattern. Value rejected." $k) -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
