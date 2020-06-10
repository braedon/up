<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" type="text/css" href="https://necolas.github.io/normalize.css/8.0.1/normalize.css">
    <link rel="stylesheet" type="text/css" href="main.css">
    <title>up?</title>
  </head>
  <body>
    <div id="content">
      <h1>up?</h1>
      <div class="message">
        % if error.body and error.status_code < 500:
        {{error.body}}
        % else:
        Oops, something went wrong
        % end
      </div>
      <div class="message">
        <a href="/">Got a link?</a>
      </div>
    </div>
  </body>
</html>
