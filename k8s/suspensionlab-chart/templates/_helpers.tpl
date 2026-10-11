{{/*
Expand the name of the chart.
*/}}
{{- define "suspensionlab.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "suspensionlab.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "suspensionlab.labels" -}}
helm.sh/chart: {{ include "suspensionlab.chart" . }}
{{ include "suspensionlab.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "suspensionlab.selectorLabels" -}}
app.kubernetes.io/name: {{ include "suspensionlab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "suspensionlab.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Authoritative Redis Address Helper
Guarantees identical host:port configuration across KEDA and Application.
Fails fast if production attempts fallback to nonexistent in-cluster Redis.
*/}}
{{- define "suspensionlab.redisAddress" -}}
{{- $isProd := or (eq (.Values.environment | default "") "production") (eq (.Values.environment | default "") "prod") -}}
{{- if and .Values.redis .Values.redis.authoritativeAddress (ne .Values.redis.authoritativeAddress "") -}}
{{- .Values.redis.authoritativeAddress -}}
{{- else if and .Values.workers .Values.workers.keda .Values.workers.keda.redisAddress (ne .Values.workers.keda.redisAddress "") -}}
{{- .Values.workers.keda.redisAddress -}}
{{- else if $isProd -}}
{{- fail "PRODUCTION CONFIGURATION ERROR: Authoritative ElastiCache Redis address must be explicitly configured via redis.authoritativeAddress or workers.keda.redisAddress. Fallback to nonexistent in-cluster Redis is strictly prohibited in production." -}}
{{- else if and .Values.redis .Values.redis.host (ne .Values.redis.host "") -}}
{{- printf "%s:%v" .Values.redis.host (.Values.redis.port | default 6379) -}}
{{- else -}}
{{- printf "%s-redis-master.%s.svc.cluster.local:6379" .Release.Name .Release.Namespace -}}
{{- end -}}
{{- end -}}

{{/*
Authoritative Redis Host Helper
*/}}
{{- define "suspensionlab.redisHost" -}}
{{- $addr := include "suspensionlab.redisAddress" . -}}
{{- $parts := split ":" $addr -}}
{{- $parts._0 -}}
{{- end -}}

{{/*
Authoritative Redis Port Helper
*/}}
{{- define "suspensionlab.redisPort" -}}
{{- $addr := include "suspensionlab.redisAddress" . -}}
{{- $parts := split ":" $addr -}}
{{- default "6379" $parts._1 -}}
{{- end -}}
