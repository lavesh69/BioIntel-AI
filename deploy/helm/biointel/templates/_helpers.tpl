{{- define "biointel.name" -}}biointel-ai{{- end }}
{{- define "biointel.fullname" -}}{{ .Release.Name }}-biointel{{- end }}
{{- define "biointel.labels" -}}
app.kubernetes.io/name: {{ include "biointel.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "biointel.selectorLabels" -}}
app.kubernetes.io/name: {{ include "biointel.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "biointel.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "biointel.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}
{{- define "biointel.claimName" -}}
{{- $root := index . 0 -}}{{- $name := index . 1 -}}{{- $cfg := index $root.Values.persistence $name -}}
{{- if $cfg.existingClaim }}{{ $cfg.existingClaim }}{{ else }}{{ include "biointel.fullname" $root }}-{{ $name }}{{ end -}}
{{- end }}
