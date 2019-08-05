# eventbot
Discord bot to streamline the organization of events for the members of a server.

# Past version history:
## v1.1
   * Add unschedule_past command
## v1.2 (heroku build 121)
   * Save datetimes as timezone aware in mongodb
   * More accurate datetime parsing and validations
   * Basic factory, teardown commands for testing
   * Improve code style
## v1.3 (heroku build 131)
   * Add basic permission system
       + Configure minimum admin role (in .py file, command soon)
       + Author may edit or delete own events
       + Admin may edit or delete any events
       + Anyone may delete all past events
   * Make more error messages temporary
## v1.3.1 (heroku build 143)
   * Minor refactoring
   * Begin implementing reminders
## v1.4 (heroku build 163)
   * Initial implementation of reminders
       + React with ⏰ emoji to receive a reminder DM 20 mins before start of event
       + Additional functionality coming soon
## v1.4.1 (heroku build 164)
   * Revised instructions to account for heroku dyno cycling clearing message cache
## v1.4.2 (heroku build 178)
   * Use raw reactions to handle reaction detection, to enable reaction functionaliy even iftarget message is not cached
   * Revise instructions to account for this bugfix
## v1.5 (heroku build 196)
   * Add guild id to metadata, allowing for use in multiple servers
   * Minor style changes to instructions message
   * Add command aliases
   * Improve !help
## v1.5.1 (heroku build 204)
   * Patch unintended deletion permissions
   * Begin work on server-specific settings
## v1.6 (heroku build 213)
   * Initial implementation of server specific timezones
## v1.6.1 (heroku build 227)
   * Timezone related bugfixes
   * Some refactoring
   * Fix duplicate time checking
## v1.6.2 (heroku build 236)
   * Initial implementation of logging
## v1.6.3
   * Additional logging
   * Improve help
## v1.6.4
   * Bugfixes
   * Guard to disallow date/time modification using !edit
## v2.0 (build 247)
   - Add flag to simplify switching between local and heroku hosting
   - Major overhaul db logic to fix bugs when bot was used in multiple servers
   - Minor refactoring/cleanup
   - Add more command aliases for !show (!s, !sh) and !schedule (!sch)
## v2.0.1 (build 248)
   - Underline event name when showing
   - Fix factory
## v2.02 (build 249)
   - Fix reschedule
## v2.03 (build 250)
   - Edit `!edit` help docs
   - Fix unschedule_past
## v2.04
   - Fix !teardown
   - Start to implement event linking
## v2.1 beta (build 266)
   - First (incomplete) release of linking
## v2.1 beta 2 (build 267)
   - Minor refactor (no more tz param in pprint_event)
   - Do not print author/description for linked event
## v2.2
   - Minor refactor (Remove some default params, comments)
   - Add id_to_name
## v2.2.1
   - Add help docs for !join
## v2.2.2
   - Add more emoji options for yes and no reactions
## v2.2.3
   - Update the formatting of the readme file

