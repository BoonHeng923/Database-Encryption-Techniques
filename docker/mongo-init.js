// Runs once on first container start (mounted into /docker-entrypoint-initdb.d/).
// Creates a project-scoped user/database, separate from the root admin account.
db = db.getSiblingDB('encbench');

db.createUser({
  user: 'encbench_user',
  pwd: 'encbench_pass',
  roles: [{ role: 'readWrite', db: 'encbench' }],
});

db.createCollection('_init_marker');
