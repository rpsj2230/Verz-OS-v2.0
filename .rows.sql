select to_jsonb(r) - 'id' from ops.acceptance_result r where run_id in (select run_id from ops.acceptance_result group by run_id order by max(started_at) desc limit 2) order by started_at, check_name
