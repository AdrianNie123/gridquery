// Cube server configuration.
//
// The stock DuckDB driver opens CUBEJS_DB_DUCKDB_DATABASE_PATH read-write and
// exposes no read-only option. The warehouse must never be writable from the
// semantic layer (dbt is the single writer), so instead of pointing the driver
// at the file we open an in-memory DuckDB and attach the warehouse READ_ONLY.
// The data volume is additionally mounted :ro in docker-compose.yml.
const { DuckDBDriver } = require('@cubejs-backend/duckdb-driver');

module.exports = {
  driverFactory: () =>
    new DuckDBDriver({
      initSql: `
        ATTACH '/data/gridquery.duckdb' AS gridquery (READ_ONLY);
        USE gridquery;
      `,
    }),
};
