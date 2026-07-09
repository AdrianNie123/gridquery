{# Use the schema configured on each folder verbatim (staging/intermediate/marts/seeds)
   instead of dbt's default main_<schema> prefixing. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
